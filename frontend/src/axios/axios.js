// src/axios/axios.js
import axios from "axios";
import { ElNotification } from "element-plus";

// 基础配置
axios.defaults.baseURL = '';
axios.defaults.headers.post['Content-Type'] = 'application/json;charset=UTF-8';

// 允许跨域携带 Cookie
axios.defaults.withCredentials = true; 

let refreshingPromise = null;
let logoutPromise = null;
let lastForceLoginAt = 0;
const lastNotificationAt = new Map();
const activeAbortControllers = new Set();

const nowMs = () => Date.now();

const isForceLoginRecentlyTriggered = () => {
  const t = nowMs();
  if (t - lastForceLoginAt < 1500) return true;
  try {
    const raw = sessionStorage.getItem("auth:force_login_at");
    const at = Number(raw || 0);
    if (Number.isFinite(at) && at > 0 && t - at < 1500) return true;
  } catch {}
  return false;
};

const notifyOnce = (key, options) => {
  if (!key) return;
  const t = nowMs();
  const last = Number(lastNotificationAt.get(key) || 0);
  if (t - last < 1500) return;
  lastNotificationAt.set(key, t);
  ElNotification(options);
};

const logoutOnce = async () => {
  if (logoutPromise) return logoutPromise;
  logoutPromise = (async () => {
    try {
      await axios.post("/api/v1/auth/logout", null, { __skipAuthHandling: true });
    } catch {}
  })();
  try {
    return await logoutPromise;
  } finally {
    logoutPromise = null;
  }
};

export const cancelAllRequests = (reason) => {
  const r = reason ? String(reason) : "canceled";
  activeAbortControllers.forEach((c) => {
    try {
      c.abort(r);
    } catch {}
  });
  activeAbortControllers.clear();
};

const attachAbortSignal = (config) => {
  if (!config || typeof config !== "object") return config;
  if (config.signal) return config;
  if (config.__skipAbortTracking) return config;
  try {
    const controller = new AbortController();
    config.signal = controller.signal;
    config.__abortController = controller;
    activeAbortControllers.add(controller);
  } catch {}
  return config;
};

const detachAbortSignal = (config) => {
  const controller = config?.__abortController;
  if (!controller) return;
  try {
    activeAbortControllers.delete(controller);
  } catch {}
  try {
    delete config.__abortController;
  } catch {}
};

const dispatchAuthRefreshed = (token) => {
  try {
    window.dispatchEvent(new CustomEvent("auth:refreshed", { detail: { token } }));
  } catch {}
};

const dispatchForceLogin = (detail) => {
  try {
    if (isForceLoginRecentlyTriggered()) return;
    lastForceLoginAt = nowMs();
    try {
      cancelAllRequests("force-login");
    } catch {}
    try {
      sessionStorage.removeItem("auth:session_cache:v1");
      sessionStorage.removeItem("auth:permissions_cache:v1");
      sessionStorage.setItem("auth:force_login_at", String(Date.now()));
      if (detail?.reason) sessionStorage.setItem("auth:force_login_reason", String(detail.reason));
    } catch {}
    window.dispatchEvent(new CustomEvent("auth:force-login", { detail: detail || {} }));
  } catch {}
};

const refreshAuth = async () => {
  if (refreshingPromise) return refreshingPromise;
  refreshingPromise = (async () => {
    const res = await axios.post("/api/v1/auth/refresh");
    dispatchAuthRefreshed(true);
    return res;
  })();
  try {
    return await refreshingPromise;
  } finally {
    refreshingPromise = null;
  }
};


// 请求拦截器 - 自动添加 token 到请求头
axios.interceptors.request.use(
  (config) => {
    return attachAbortSignal(config);
  },
  (error) => Promise.reject(error)
);

// 响应拦截器 - 处理认证失败等情况
axios.interceptors.response.use(
  (response) => {
    try {
      detachAbortSignal(response?.config);
    } catch {}
    return response;
  },
  async (error) => {
    const status = error?.response?.status;
    const data = error?.response?.data || {};
    const errCode = data.error;
    const originalConfig = error?.config || {};
    try {
      detachAbortSignal(originalConfig);
    } catch {}
    const url = String(originalConfig?.url || "");
    if (originalConfig.__skipAuthHandling) return Promise.reject(error);

    if (status === 401 && errCode === "AUTH_SESSION_REVOKED") {
      const device = data?.data?.new_login?.device;
      const ip = data?.data?.new_login?.ip;
      try {
        const payload = data?.data?.new_login ?? null;
        sessionStorage.setItem("auth:kicked_info", JSON.stringify(payload));
      } catch {}
      try {
        await logoutOnce();
      } catch {}
      if (!isForceLoginRecentlyTriggered()) {
        notifyOnce("force-login:kicked", {
          title: "登录已失效",
          message: data.message || (device || ip ? `已在其他设备登录（${String(device || "未知设备")} / ${String(ip || "未知IP")}）` : "会话已失效，请重新登录"),
          type: "warning",
        });
      }
      dispatchForceLogin({ reason: "kicked" });
      return Promise.reject(error);
    }

    if (status === 401 && errCode === "AUTH_ACCOUNT_DISABLED") {
      try {
        await logoutOnce();
      } catch {}
      if (!isForceLoginRecentlyTriggered()) {
        notifyOnce("force-login:disabled", {
          title: "账号已封禁",
          message: data.message || "账号已封禁或已删除，请联系管理员",
          type: "warning",
        });
      }
      dispatchForceLogin({ reason: "disabled" });
      return Promise.reject(error);
    }

    if (status === 401) {
      if (url.includes("/api/v1/auth/refresh")) return Promise.reject(error);
      if (url.includes("/api/v1/auth/logout")) return Promise.reject(error);
      if (!originalConfig.__authRefreshed) {
        originalConfig.__authRefreshed = true;
        try {
          await refreshAuth();
          return axios(originalConfig);
        } catch (e) {
          const refreshData = e?.response?.data || {};
          const refreshErrCode = refreshData?.error;
          const refreshDevice = refreshData?.data?.new_login?.device;
          const refreshIp = refreshData?.data?.new_login?.ip;
          try {
            await logoutOnce();
          } catch {}
          if (refreshErrCode === "AUTH_SESSION_REVOKED") {
            try {
              const payload = refreshData?.data?.new_login ?? null;
              sessionStorage.setItem("auth:kicked_info", JSON.stringify(payload));
            } catch {}
            if (!isForceLoginRecentlyTriggered()) {
              notifyOnce("force-login:kicked", {
                title: "登录已失效",
                message:
                  refreshData.message ||
                  (refreshDevice || refreshIp
                    ? `已在其他设备登录（${String(refreshDevice || "未知设备")} / ${String(refreshIp || "未知IP")}）`
                    : "会话已失效，请重新登录"),
                type: "warning",
              });
            }
            dispatchForceLogin({ reason: "kicked" });
            return Promise.reject(error);
          }
          if (refreshErrCode === "AUTH_ACCOUNT_DISABLED") {
            if (!isForceLoginRecentlyTriggered()) {
              notifyOnce("force-login:disabled", {
                title: "账号已封禁",
                message: refreshData.message || "账号已封禁或已删除，请联系管理员",
                type: "warning",
              });
            }
            dispatchForceLogin({ reason: "disabled" });
            return Promise.reject(error);
          }
          if (!isForceLoginRecentlyTriggered()) {
            notifyOnce("force-login:expired", {
              title: "登录已失效",
              message: refreshData.message || "认证已过期，请重新登录",
              type: "warning",
            });
          }
          dispatchForceLogin({ reason: "expired" });
          return Promise.reject(error);
        }
      }
    }

    return Promise.reject(error);
  }
);

export default axios;
