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

      <div v-if="kickedInfo" class="kick-panel">
        <div class="kick-panel__header">
          <div class="kick-panel__badge">安全提醒</div>
          <div class="kick-panel__title">当前登录已失效</div>
          <div class="kick-panel__desc">你的账号刚刚在另一台设备完成登录，因此当前页面已自动退出。</div>
        </div>

        <div class="kick-meta">
          <div class="kick-meta__item">
            <span class="kick-meta__label">登录设备</span>
            <span class="kick-meta__value">{{ kickedInfo.device || '未知设备' }}</span>
          </div>
          <div class="kick-meta__item">
            <span class="kick-meta__label">登录 IP</span>
            <span class="kick-meta__value">{{ kickedInfo.ip || '未知 IP' }}</span>
          </div>
          <div v-if="formatKickedTime(kickedInfo.ts)" class="kick-meta__item">
            <span class="kick-meta__label">登录时间</span>
            <span class="kick-meta__value">{{ formatKickedTime(kickedInfo.ts) }}</span>
          </div>
        </div>

        <div class="kick-note">
          <span v-if="isLikelySelfLogin">如果这是你本人刚刚在其他设备上的登录，可以直接在当前页面重新登录。</span>
          <span v-else>如果这次登录不是你本人操作，建议尽快重置密码并检查账号安全设置。</span>
        </div>

        <div class="kick-actions">
          <el-button type="primary" @click="goForgotPassword">立即重置密码</el-button>
          <el-button text @click="clearKickedInfo">我知道了</el-button>
        </div>
      </div>

      <el-form :model="form" label-position="top" @keyup.enter="submitLogin">
        <el-form-item label="账号">
          <el-input v-model="form.username" placeholder="请输入账号" :prefix-icon="User" />
        </el-form-item>

        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="请输入密码" :prefix-icon="Lock" />
        </el-form-item>

        <el-form-item v-if="captchaRequired" label="验证码">
          <div class="captcha-row">
            <div class="captcha-image-box">
              <img v-if="form.captchaImage" :src="form.captchaImage" alt="captcha" class="captcha-image" />
              <span v-else class="captcha-placeholder">加载中...</span>
            </div>
            <el-input v-model="form.captchaCode" placeholder="请输入验证码" style="flex: 1" />
            <el-button :disabled="captchaLoading" :loading="captchaLoading" @click="refreshCaptcha">刷新</el-button>
          </div>
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
import { computed, reactive, ref, onMounted, watch } from 'vue' // 引入 Vue 响应式 API
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
  captchaId: '',
  captchaImage: '',
  captchaCode: '',
})

const rememberPassword = ref(false) // 是否记住账号（这里变量名 rememberPassword 实际上是“记住账号”，逻辑上有点歧义，但保留原意）
const loading = ref(false) // 登录按钮的加载状态
const kickedInfo = ref(null) // 存储被踢出登录的信息
const captchaRequired = ref(false)
const captchaLoading = ref(false)

const formatKickedTime = (value) => {
  if (!value) return ''
  const raw = String(value).trim()
  if (!raw) return ''
  const date = new Date(raw)
  if (Number.isNaN(date.getTime())) return raw
  return date.toLocaleString('zh-CN', { hour12: false })
}

const isLikelySelfLogin = computed(() => {
  if (!kickedInfo.value) return false
  return Boolean(kickedInfo.value.device || kickedInfo.value.ip)
})

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

const clearKickedInfo = () => {
  kickedInfo.value = null
  try {
    sessionStorage.removeItem('auth:kicked_info')
  } catch {}
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

const refreshCaptcha = async () => {
  captchaLoading.value = true
  try {
    const prevCaptchaId = String(form.captchaId || '').trim()
    const res = await axios.get('/api/v1/auth/captcha', {
      params: prevCaptchaId ? { prev_captcha_id: prevCaptchaId } : undefined,
      __skipAuthHandling: true,
    })
    form.captchaId = String(res?.data?.data?.captcha_id || '')
    const imageBase64 = String(res?.data?.data?.image_base64 || '')
    const imageMime = String(res?.data?.data?.image_mime || 'image/png')
    form.captchaImage = imageBase64 ? `data:${imageMime};base64,${imageBase64}` : ''
    form.captchaCode = ''
  } catch (err) {
    ElNotification({
      title: 'Error',
      message: err.response?.data?.message || err.message || '验证码加载失败',
      type: 'error',
    })
  } finally {
    captchaLoading.value = false
  }
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
  if (captchaRequired.value) {
    const captchaId = String(form.captchaId || '').trim()
    const captchaCode = String(form.captchaCode || '').trim()
    if (!captchaId || !captchaCode) {
      ElNotification({ title: 'Error', message: '请完成验证码', type: 'error' })
      return
    }
  }

  loading.value = true // 开启加载状态
  try {
    // 发送登录请求
    const payload = { username, password }
    if (captchaRequired.value) {
      payload.captcha_id = String(form.captchaId || '').trim()
      payload.captcha_code = String(form.captchaCode || '').trim()
    }
    const res = await axios.post('/api/v1/auth/login', payload, { __skipAuthHandling: true })
    try {
      // 登录成功后，清除强制登录标记
      sessionStorage.removeItem('auth:force_login_at')
      sessionStorage.removeItem('auth:force_login_reason')
    } catch {}
    captchaRequired.value = false
    form.captchaId = ''
    form.captchaImage = ''
    form.captchaCode = ''

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
    const errCode = err?.response?.data?.error
    const serverCaptchaRequired = Boolean(err?.response?.data?.data?.captcha_required)
    if (serverCaptchaRequired || String(errCode || '').startsWith('AUTH_CAPTCHA')) {
      captchaRequired.value = true
      await refreshCaptcha()
    }
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

.kick-panel {
  margin: 10px 0 14px;
  padding: 16px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(255, 247, 237, 0.98), rgba(255, 251, 235, 0.96));
  border: 1px solid rgba(245, 158, 11, 0.22);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.kick-panel__header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kick-panel__badge {
  width: fit-content;
  padding: 3px 8px;
  border-radius: 999px;
  background: rgba(245, 158, 11, 0.14);
  color: #b45309;
  font-size: 12px;
  font-weight: 700;
}

.kick-panel__title {
  font-size: 17px;
  font-weight: 700;
  color: #111827;
}

.kick-panel__desc {
  font-size: 13px;
  line-height: 1.6;
  color: #6b7280;
}

.kick-meta {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 14px;
}

.kick-meta__item {
  min-width: 0;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px solid rgba(251, 191, 36, 0.18);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.kick-meta__label {
  font-size: 12px;
  color: #9ca3af;
}

.kick-meta__value {
  font-size: 13px;
  font-weight: 600;
  color: #1f2937;
  word-break: break-all;
}

.kick-note {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.62);
  color: #4b5563;
  font-size: 13px;
  line-height: 1.7;
}

.kick-actions {
  margin-top: 12px;
  display: flex;
  gap: 10px;
  align-items: center;
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

.captcha-row {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.captcha-image-box {
  width: 240px;
  height: 96px;
  border-radius: 8px;
  overflow: hidden;
  background: rgba(17, 24, 39, 0.06);
  border: 1px solid rgba(17, 24, 39, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
}

.captcha-image {
  width: 100%;
  height: 100%;
  object-fit: contain;
  display: block;
}

.captcha-placeholder {
  color: #6b7280;
  font-size: 12px;
  text-align: center;
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

  .kick-meta {
    grid-template-columns: 1fr;
  }

  .auth-brand h1 {
    font-size: 1.9rem;
  }
}
</style>
