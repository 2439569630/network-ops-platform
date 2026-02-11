// src/axios/axios.js
import axios from "axios";
import { ElNotification } from "element-plus";

// 基础配置
axios.defaults.baseURL = '';
axios.defaults.headers.post['Content-Type'] = 'application/json;charset=UTF-8';

// 允许跨域携带 Cookie
axios.defaults.withCredentials = true; 

let refreshingPromise = null;

const dispatchAuthRefreshed = (token) => {
  try {
    window.dispatchEvent(new CustomEvent("auth:refreshed", { detail: { token } }));
  } catch {}
};

const dispatchForceLogin = (detail) => {
  try {
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
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器 - 处理认证失败等情况
axios.interceptors.response.use(
  (response) => response,
  async (error) => {
    const status = error?.response?.status;
    const data = error?.response?.data || {};
    const errCode = data.error;
    const originalConfig = error?.config || {};
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
        await axios.post("/api/v1/auth/logout", null, { __skipAuthHandling: true });
      } catch {}
      ElNotification({
        title: "登录已失效",
        message: data.message || (device || ip ? `已在其他设备登录（${String(device || "未知设备")} / ${String(ip || "未知IP")}）` : "会话已失效，请重新登录"),
        type: "warning",
      });
      dispatchForceLogin({ reason: "kicked" });
      return Promise.reject(error);
    }

    if (status === 401 && errCode === "AUTH_ACCOUNT_DISABLED") {
      try {
        await axios.post("/api/v1/auth/logout", null, { __skipAuthHandling: true });
      } catch {}
      ElNotification({
        title: "账号已封禁",
        message: data.message || "账号已封禁或已删除，请联系管理员",
        type: "warning",
      });
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
          try {
            await axios.post("/api/v1/auth/logout", null, { __skipAuthHandling: true });
          } catch {}
          ElNotification({
            title: "登录已失效",
            message: data.message || "认证已过期，请重新登录",
            type: "warning",
          });
          dispatchForceLogin({ reason: "expired" });
          return Promise.reject(error);
        }
      }
    }

    return Promise.reject(error);
  }
);

export default axios;
