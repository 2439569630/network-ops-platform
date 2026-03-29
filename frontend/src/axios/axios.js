// src/axios/axios.js
import axios from "axios"; // 引入 Axios 库
import { ElNotification } from "element-plus"; // 引入通知组件

// 基础配置
axios.defaults.baseURL = ''; // 设置基础 URL，这里为空字符串，通常由代理或相对路径处理
axios.defaults.headers.post['Content-Type'] = 'application/json;charset=UTF-8'; // 设置 POST 请求的默认 Content-Type

// 允许跨域携带 Cookie，这对于基于 Cookie 的认证非常重要
axios.defaults.withCredentials = true; 

// 定义全局变量，用于管理请求状态和防止重复操作
let refreshingPromise = null; // 存储 Token 刷新的 Promise，防止并发刷新
let logoutPromise = null; // 存储登出操作的 Promise
let lastForceLoginAt = 0; // 上次强制登录的时间戳，用于防止短时间内多次触发
const lastNotificationAt = new Map(); // 记录每种通知类型的上次触发时间
const activeAbortControllers = new Set(); // 存储所有活动的 AbortController，用于取消请求

const nowMs = () => Date.now(); // 获取当前时间戳的辅助函数

// 检查是否最近触发过强制登录，防止弹窗轰炸
const isForceLoginRecentlyTriggered = () => {
  const t = nowMs();
  if (t - lastForceLoginAt < 1500) return true; // 如果 1.5 秒内触发过，返回 true
  try {
    const raw = sessionStorage.getItem("auth:force_login_at");
    const at = Number(raw || 0);
    if (Number.isFinite(at) && at > 0 && t - at < 1500) return true; // 检查 sessionStorage 中的记录
  } catch {}
  return false;
};

// 确保同一类型的通知在短时间内只显示一次
const notifyOnce = (key, options) => {
  if (!key) return;
  const t = nowMs();
  const last = Number(lastNotificationAt.get(key) || 0);
  if (t - last < 1500) return; // 1.5 秒冷却时间
  lastNotificationAt.set(key, t);
  ElNotification(options); // 显示通知
};

// 执行登出操作，并确保同一时间只有一个登出请求在进行
const logoutOnce = async () => {
  if (logoutPromise) return logoutPromise; // 如果已有登出请求，直接返回该 Promise
  logoutPromise = (async () => {
    try {
      // 发送登出请求，__skipAuthHandling 标志表示跳过认证错误处理
      await axios.post("/api/v1/auth/logout", null, { __skipAuthHandling: true });
    } catch {}
  })();
  try {
    return await logoutPromise;
  } finally {
    logoutPromise = null; // 请求完成后重置 Promise
  }
};

// 取消所有挂起的请求，通常在路由跳转或强制登出时调用
export const cancelAllRequests = (reason) => {
  const r = reason ? String(reason) : "canceled";
  activeAbortControllers.forEach((c) => {
    try {
      c.abort(r); // 中止请求
    } catch {}
  });
  activeAbortControllers.clear(); // 清空控制器集合
};

// 为请求配置附加 AbortController，以便后续可以取消该请求
const attachAbortSignal = (config) => {
  if (!config || typeof config !== "object") return config;
  if (config.signal) return config; // 如果已经有 signal，则不处理
  if (config.__skipAbortTracking) return config; // 如果标记为跳过跟踪，则不处理
  try {
    const controller = new AbortController();
    config.signal = controller.signal;
    config.__abortController = controller; // 将 controller 挂载到 config 上
    activeAbortControllers.add(controller); // 添加到活跃集合中
  } catch {}
  return config;
};

// 请求完成后，移除相关的 AbortController
const detachAbortSignal = (config) => {
  const controller = config?.__abortController;
  if (!controller) return;
  try {
    activeAbortControllers.delete(controller); // 从集合中移除
  } catch {}
  try {
    delete config.__abortController; // 清理 config 对象
  } catch {}
};

// 分发 Token 刷新成功事件
const dispatchAuthRefreshed = (token) => {
  try {
    window.dispatchEvent(new CustomEvent("auth:refreshed", { detail: { token } }));
  } catch {}
};

// 分发强制登录事件，处理清理工作和状态记录
const dispatchForceLogin = (detail) => {
  try {
    if (isForceLoginRecentlyTriggered()) return; // 避免重复触发
    lastForceLoginAt = nowMs();
    try {
      cancelAllRequests("force-login"); // 取消所有请求
    } catch {}
    try {
      // 清除会话缓存
      sessionStorage.removeItem("auth:session_cache:v1");
      sessionStorage.removeItem("auth:permissions_cache:v1");
      // 记录强制登录时间和原因
      sessionStorage.setItem("auth:force_login_at", String(Date.now()));
      if (detail?.reason) sessionStorage.setItem("auth:force_login_reason", String(detail.reason));
    } catch {}
    // 触发自定义事件，main.js 中会监听此事件进行跳转
    window.dispatchEvent(new CustomEvent("auth:force-login", { detail: detail || {} }));
  } catch {}
};

// 刷新 Token 的逻辑
const refreshAuth = async () => {
  if (refreshingPromise) return refreshingPromise; // 避免并发刷新
  refreshingPromise = (async () => {
    // 调用刷新接口
    const res = await axios.post("/api/v1/auth/refresh");
    dispatchAuthRefreshed(true); // 通知刷新成功
    return res;
  })();
  try {
    return await refreshingPromise;
  } finally {
    refreshingPromise = null; // 重置 Promise
  }
};


// 请求拦截器 - 自动添加 token 到请求头（这里主要处理 AbortSignal）
axios.interceptors.request.use(
  (config) => {
    return attachAbortSignal(config); // 附加 AbortSignal
  },
  (error) => Promise.reject(error)
);

// 响应拦截器 - 处理认证失败等情况
axios.interceptors.response.use(
  (response) => {
    try {
      detachAbortSignal(response?.config); // 成功响应后清理 AbortController
    } catch {}
    return response;
  },
  async (error) => {
    const status = error?.response?.status;
    const data = error?.response?.data || {};
    const errCode = data.error;
    const originalConfig = error?.config || {};
    try {
      detachAbortSignal(originalConfig); // 失败响应后清理 AbortController
    } catch {}
    const url = String(originalConfig?.url || "");
    // 如果配置了跳过认证处理，直接拒绝
    if (originalConfig.__skipAuthHandling) return Promise.reject(error);

    // 处理被踢出登录的情况
    if (status === 401 && errCode === "AUTH_SESSION_REVOKED") {
      const device = data?.data?.new_login?.device;
      const ip = data?.data?.new_login?.ip;
      try {
        const payload = data?.data?.new_login ?? null;
        sessionStorage.setItem("auth:kicked_info", JSON.stringify(payload));
      } catch {}
      try {
        await logoutOnce(); // 尝试登出
      } catch {}
      if (!isForceLoginRecentlyTriggered()) {
        notifyOnce("force-login:kicked", {
          title: "当前登录已退出",
          message:
            data.message ||
            (device || ip
              ? `账号已在新设备完成登录，当前页面已退出。设备：${String(device || "未知设备")}，IP：${String(ip || "未知IP")}`
              : "账号已在其他设备登录，当前页面已退出，请重新登录"),
          type: "warning",
        });
      }
      dispatchForceLogin({ reason: "kicked" }); // 触发强制登录
      return Promise.reject(error);
    }

    // 处理账号被封禁的情况
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

    // 处理一般 401 错误，尝试刷新 Token
    if (status === 401) {
      // 如果是刷新 Token 或登出接口本身的 401，则不重试
      if (url.includes("/api/v1/auth/refresh")) return Promise.reject(error);
      if (url.includes("/api/v1/auth/logout")) return Promise.reject(error);
      
      // 如果没有重试过
      if (!originalConfig.__authRefreshed) {
        originalConfig.__authRefreshed = true; // 标记已重试
        try {
          await refreshAuth(); // 尝试刷新 Token
          return axios(originalConfig); // 刷新成功后重试原请求
        } catch (e) {
          // 刷新失败，处理各种原因
          const refreshData = e?.response?.data || {};
          const refreshErrCode = refreshData?.error;
          const refreshDevice = refreshData?.data?.new_login?.device;
          const refreshIp = refreshData?.data?.new_login?.ip;
          try {
            await logoutOnce();
          } catch {}
          // 刷新失败原因：被踢出
          if (refreshErrCode === "AUTH_SESSION_REVOKED") {
            try {
              const payload = refreshData?.data?.new_login ?? null;
              sessionStorage.setItem("auth:kicked_info", JSON.stringify(payload));
            } catch {}
            if (!isForceLoginRecentlyTriggered()) {
              notifyOnce("force-login:kicked", {
                title: "当前登录已退出",
                message:
                  refreshData.message ||
                  (refreshDevice || refreshIp
                    ? `账号已在新设备完成登录，当前页面已退出。设备：${String(refreshDevice || "未知设备")}，IP：${String(refreshIp || "未知IP")}`
                    : "账号已在其他设备登录，当前页面已退出，请重新登录"),
                type: "warning",
              });
            }
            dispatchForceLogin({ reason: "kicked" });
            return Promise.reject(error);
          }
          // 刷新失败原因：账号封禁
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
          // 刷新失败原因：过期
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
