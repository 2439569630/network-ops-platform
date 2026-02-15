<template>
  <div class="auth-page">
    <div class="auth-brand">
      <h1>网络设备自动化运维平台</h1>
    </div>

    <el-card class="auth-card" shadow="never">
      <div class="auth-header">
        <div class="auth-title">登录</div>
        <div class="auth-subtitle">使用账号密码登录系统</div>
      </div>

      <el-alert
        v-if="kickedInfo"
        class="kick-alert"
        title="你的账号已在另一台设备登录"
        type="warning"
        :closable="false"
        show-icon
      >
        <template #default>
          <div class="kick-body">
            <div class="kick-line">
              新登录设备：{{ kickedInfo.device || '未知' }}
            </div>
            <div class="kick-line">
              新登录IP：{{ kickedInfo.ip || '未知' }}
            </div>
            <div class="kick-line" v-if="kickedInfo.ts">
              时间：{{ kickedInfo.ts }}
            </div>
            <div class="kick-line">
              如果不是你本人操作，可能密码已泄露，建议立即重置密码。
            </div>
            <div class="kick-actions">
              <el-button type="primary" @click="goForgotPassword">通过邮箱重置密码</el-button>
            </div>
          </div>
        </template>
      </el-alert>

      <el-form :model="form" label-position="top" @keyup.enter="submitLogin">
        <el-form-item label="账号">
          <el-input v-model="form.username" placeholder="请输入账号" :prefix-icon="User" />
        </el-form-item>

        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" />
        </el-form-item>

         <div class="auth-row">
          <el-checkbox v-model="rememberPassword">记住账号</el-checkbox>
          <el-button type="primary" link @click="goForgotPassword">忘记密码</el-button>
        </div>
      </el-form>

      <div class="auth-actions">
        <el-button @click="goRegister">去注册</el-button>
        <el-button type="primary" :loading="loading" @click="submitLogin">登录</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted, watch } from 'vue' // 引入 Vue 响应式 API
import { useRoute, useRouter } from 'vue-router' // 引入 Vue Router 钩子
import axios from '@/axios/axios' // 引入封装的 Axios
import { ElNotification } from 'element-plus' // 引入 Element Plus 通知组件
import { User, Lock } from '@element-plus/icons-vue' // 引入图标
import { homeDataStore } from '@/components/home/home/data' // 引入主页数据 Store

const router = useRouter() // 获取 Router 实例
const route = useRoute() // 获取当前路由信息

// 定义登录表单数据，使用 reactive 保持响应式
const form = reactive({
  username: '',
  password: '',
})

const rememberPassword = ref(false) // 是否记住账号（这里变量名 rememberPassword 实际上是“记住账号”，逻辑上有点歧义，但保留原意）
const loading = ref(false) // 登录按钮的加载状态
const kickedInfo = ref(null) // 存储被踢出登录的信息

// 加载被踢出登录的信息
const loadKickedInfo = () => {
  try {
    const reason = String(route.query?.reason || '')
    // 如果原因不是被踢出，则清空信息
    if (reason !== 'kicked') {
      kickedInfo.value = null
      return
    }
    // 从 sessionStorage 获取详细信息
    const raw = sessionStorage.getItem('auth:kicked_info')
    kickedInfo.value = raw ? JSON.parse(raw) : { device: null, ip: null }
    sessionStorage.removeItem('auth:kicked_info') // 获取后立即清除，避免重复显示
  } catch {
    kickedInfo.value = null
  }
}

// 组件挂载时执行
onMounted(() => {
  loadKickedInfo() // 加载踢出信息

  // 尝试从 localStorage 获取缓存的用户名
  const cachedUser = localStorage.getItem('username')
  if (cachedUser) {
    form.username = cachedUser
    rememberPassword.value = true // 如果有缓存，默认勾选“记住账号”
    return
  }
  // 如果 URL 中有用户名参数，自动填充
  const qUser = route.query?.username
  if (typeof qUser === 'string' && qUser.trim()) {
    form.username = qUser.trim()
  }
})

// 监听路由参数变化，如果 reason 变为 kicked，重新加载信息
watch(
  () => route.query?.reason,
  () => {
    loadKickedInfo()
  }
)

// 跳转到注册页
const goRegister = () => {
  router.push('/register')
}

// 跳转到忘记密码页
const goForgotPassword = () => {
  router.push('/forgot-password')
}

// 登录成功后，根据用户权限选择跳转路径
const pickPostLoginPath = async () => {
  const fallback = '/user/home' // 默认跳转路径
  const store = homeDataStore()
  // 确保会话已建立，force: true 表示强制刷新用户信息
  const session = await store.ensureSession({ force: true })
  if (!session) return fallback
  if (store.isSuper) return '/user/dashboard' // 超级管理员跳转到仪表盘

  try {
    // 获取权限列表
    const perms = await store.fetchPermissions({ force: true })
    if (perms.includes('sys:dashboard:view')) return '/user/dashboard'
    if (perms.includes('sys:message:access')) return '/user/message'
    return fallback
  } catch (e) {
    return fallback
  }
}

// 提交登录表单
const submitLogin = async () => {
  const username = String(form.username || '').trim()
  const password = String(form.password || '')
  // 简单验证
  if (!username || !password) {
    ElNotification({ title: 'Error', message: '账号或密码不能为空', type: 'error' })
    return
  }

  loading.value = true // 开启加载状态
  try {
    // 发送登录请求
    const res = await axios.post('/api/v1/auth/login', { username, password })
    try {
      // 登录成功后，清除强制登录标记
      sessionStorage.removeItem('auth:force_login_at')
      sessionStorage.removeItem('auth:force_login_reason')
    } catch {}

    // 处理“记住账号”逻辑
    if (rememberPassword.value) {
      localStorage.setItem('username', username)
    } else {
      localStorage.removeItem('username')
    }

    // 获取跳转路径并跳转
    const nextPath = await pickPostLoginPath()
    await router.push(nextPath)

    ElNotification({
      title: 'Success',
      message: res.data?.message || '登录成功',
      type: 'success',
    })
  } catch (err) {
    // 登录失败处理
    ElNotification({
      title: 'Error',
      message: err.response?.data?.message || err.message || '登录失败',
      type: 'error',
    })
  } finally {
    loading.value = false // 关闭加载状态
  }
}
</script>
<style scoped>
.auth-page {
  width: 100%;
  height: 100vh;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
  padding: 24px 12px;
  position: relative;
}

.auth-brand {
  display: flex;
  align-items: center;
  margin-bottom: 18px;
  z-index: 1;
}

.auth-brand h1 {
  font-size: 2.3rem;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
  margin: 0;
}

.auth-card {
  width: 520px;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.35);
  background: rgba(255, 255, 255, 0.95);
  backdrop-filter: blur(12px);
  box-shadow: 0 18px 40px rgba(0, 0, 0, 0.18);
  z-index: 1;
}

.kick-alert {
  margin: 10px 0 12px;
}

.kick-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.kick-line {
  color: #374151;
  font-size: 13px;
}

.kick-actions {
  margin-top: 8px;
}

.auth-header {
  padding-bottom: 10px;
  border-bottom: 1px solid #eef2f7;
  margin-bottom: 12px;
}

.auth-title {
  font-size: 18px;
  font-weight: 700;
  color: #111827;
}

.auth-subtitle {
  margin-top: 4px;
  font-size: 13px;
  color: #6b7280;
}

.auth-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: -4px;
}

.auth-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}

.auth-page::before {
  content: '';
  position: absolute;
  width: 220px;
  height: 220px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.1);
  top: 10%;
  left: 10%;
  animation: float 6s ease-in-out infinite;
}

.auth-page::after {
  content: '';
  position: absolute;
  width: 160px;
  height: 160px;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.06);
  bottom: 10%;
  right: 10%;
  animation: float 8s ease-in-out infinite reverse;
}

@keyframes float {
  0%,
  100% {
    transform: translateY(0) rotate(0deg);
  }
  50% {
    transform: translateY(-18px) rotate(180deg);
  }
}

@media (max-width: 640px) {
  .auth-card {
    width: 100%;
    max-width: 520px;
  }
  .auth-brand h1 {
    font-size: 1.9rem;
  }
}
</style>
