// src/axios/axios.js
import axios from "axios";
import Cookies from "js-cookie";
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

const refreshAuth = async () => {
  if (refreshingPromise) return refreshingPromise;
  refreshingPromise = (async () => {
    const res = await axios.post("/api/v1/auth/refresh");
    const nextToken = res?.data?.token;
    if (nextToken) {
      Cookies.set("token", nextToken, { sameSite: "lax" });
      dispatchAuthRefreshed(nextToken);
    } else {
      dispatchAuthRefreshed(null);
    }
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

    if (status === 401 && (errCode === "AUTH_TOKEN_TOO_OLD" || errCode === "AUTHZ_VERSION_MISMATCH")) {
      const originalConfig = error?.config || {};
      const url = String(originalConfig?.url || "");
      if (url.includes("/api/v1/auth/refresh")) return Promise.reject(error);
      if (!originalConfig.__authRefreshed) {
        originalConfig.__authRefreshed = true;
        try {
          await refreshAuth();
          return axios(originalConfig);
        } catch (e) {
          Cookies.remove("token");
          ElNotification({
            title: "登录已失效",
            message: data.message || "权限已更新，请重新登录",
            type: "warning",
          });
          window.location.href = "/login";
          return Promise.reject(error);
        }
      }
    }

    return Promise.reject(error);
  }
);

export default axios;
