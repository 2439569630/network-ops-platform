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
import { reactive, ref, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from '@/axios/axios'
import { ElNotification } from 'element-plus'
import { User, Lock } from '@element-plus/icons-vue'
import { homeDataStore } from '@/components/home/home/data'

const router = useRouter()
const route = useRoute()

const form = reactive({
  username: '',
  password: '',
})

const rememberPassword = ref(false)
const loading = ref(false)
const kickedInfo = ref(null)

const loadKickedInfo = () => {
  try {
    const reason = String(route.query?.reason || '')
    if (reason !== 'kicked') {
      kickedInfo.value = null
      return
    }
    const raw = sessionStorage.getItem('auth:kicked_info')
    kickedInfo.value = raw ? JSON.parse(raw) : { device: null, ip: null }
    sessionStorage.removeItem('auth:kicked_info')
  } catch {
    kickedInfo.value = null
  }
}

onMounted(() => {
  loadKickedInfo()

  const cachedUser = localStorage.getItem('username')
  if (cachedUser) {
    form.username = cachedUser
    rememberPassword.value = true
    return
  }
  const qUser = route.query?.username
  if (typeof qUser === 'string' && qUser.trim()) {
    form.username = qUser.trim()
  }
})

watch(
  () => route.query?.reason,
  () => {
    loadKickedInfo()
  }
)

const goRegister = () => {
  router.push('/register')
}

const goForgotPassword = () => {
  router.push('/forgot-password')
}

const pickPostLoginPath = async () => {
  const fallback = '/user/home'
  const store = homeDataStore()
  const session = await store.ensureSession({ force: true })
  if (!session) return fallback
  if (store.isSuper) return '/user/dashboard'

  try {
    const perms = await store.fetchPermissions({ force: true })
    if (perms.includes('sys:dashboard:view')) return '/user/dashboard'
    if (perms.includes('sys:message:access')) return '/user/message'
    return fallback
  } catch (e) {
    return fallback
  }
}

const submitLogin = async () => {
  const username = String(form.username || '').trim()
  const password = String(form.password || '')
  if (!username || !password) {
    ElNotification({ title: 'Error', message: '账号或密码不能为空', type: 'error' })
    return
  }

  loading.value = true
  try {
    const res = await axios.post('/api/v1/auth/login', { username, password })

    if (rememberPassword.value) {
      localStorage.setItem('username', username)
    } else {
      localStorage.removeItem('username')
    }

    const nextPath = await pickPostLoginPath()
    await router.push(nextPath)

    ElNotification({
      title: 'Success',
      message: res.data?.message || '登录成功',
      type: 'success',
    })
  } catch (err) {
    ElNotification({
      title: 'Error',
      message: err.response?.data?.message || err.message || '登录失败',
      type: 'error',
    })
  } finally {
    loading.value = false
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
