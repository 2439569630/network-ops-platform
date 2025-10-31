// src/axios/axios.js
import axios from "axios";
import { ElMessage } from 'element-plus';
import router from '@/router';

// 基础配置
axios.defaults.baseURL = 'http://127.0.0.1:8000';
axios.defaults.headers.post['Content-Type'] = 'application/json;charset=UTF-8';

// 允许跨域携带 Cookie
axios.defaults.withCredentials = true; 



// 请求拦截器 - 自动添加 token 到请求头
axios.interceptors.request.use(
 
);

// 响应拦截器 - 处理认证失败等情况
axios.interceptors.response.use(
 
);

export default axios;