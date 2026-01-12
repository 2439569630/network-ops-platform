<template>
  <div class="auth-page">
    <div class="auth-brand">
      <h1>网络设备自动化运维平台</h1>
    </div>

    <el-card class="auth-card" shadow="never">
      <div class="auth-header">
        <div class="auth-title">{{ hasToken ? '重置密码' : '忘记密码' }}</div>
        <div class="auth-subtitle">
          {{ hasToken ? '通过邮件链接设置新密码' : '输入邮箱并完成验证码，系统将发送重置链接' }}
        </div>
      </div>

      <template v-if="!hasToken">
        <el-form :model="requestForm" label-position="top" @keyup.enter="submitRequest">
          <el-form-item label="邮箱">
            <el-input v-model="requestForm.email" placeholder="请输入绑定邮箱" :prefix-icon="Message" />
          </el-form-item>

          <el-form-item label="验证码">
            <div class="captcha-row">
              <div class="captcha-question">{{ requestForm.captchaQuestion || '加载中...' }}</div>
              <el-input v-model="requestForm.captchaAnswer" placeholder="请输入答案" style="flex: 1" />
              <el-button :disabled="captchaLoading" :loading="captchaLoading" @click="refreshCaptcha">刷新</el-button>
            </div>
          </el-form-item>
        </el-form>

        <el-alert
          v-if="sent"
          title="如果邮箱已绑定，将发送重置链接，请查收邮箱继续操作"
          type="success"
          :closable="false"
          style="margin-top: 12px"
        />
      </template>

      <template v-else>
        <el-form :model="resetForm" label-position="top" @keyup.enter="submitReset">
          <el-form-item label="新密码">
            <el-input v-model="resetForm.password" type="password" show-password placeholder="至少 6 位" :prefix-icon="Lock" />
          </el-form-item>

          <el-form-item label="确认新密码">
            <el-input v-model="resetForm.password2" type="password" show-password placeholder="再次输入新密码" :prefix-icon="Lock" />
          </el-form-item>
        </el-form>
      </template>

      <div class="auth-actions">
        <el-button @click="goLogin">返回登录</el-button>
        <el-button
          v-if="!hasToken"
          type="primary"
          :disabled="cooldownLeft > 0"
          :loading="submitting"
          @click="submitRequest"
        >
          {{ cooldownLeft > 0 ? `${cooldownLeft}s` : '发送重置链接' }}
        </el-button>
        <el-button v-else type="primary" :loading="submitting" @click="submitReset">重置密码</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, reactive, ref, onMounted, onUnmounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from '@/axios/axios'
import { ElNotification } from 'element-plus'
import { Lock, Message } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()

const token = computed(() => (typeof route.query?.token === 'string' ? route.query.token.trim() : ''))
const hasToken = computed(() => Boolean(token.value))

const requestForm = reactive({
  email: '',
  captchaId: '',
  captchaQuestion: '',
  captchaAnswer: '',
})

const resetForm = reactive({
  password: '',
  password2: '',
})

const captchaLoading = ref(false)
const submitting = ref(false)
const cooldownLeft = ref(0)
const sent = ref(false)
let cooldownTimer = null

const isValidEmail = (email) => {
  const v = String(email || '').trim()
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)
}

const startCooldown = (seconds) => {
  const total = Number(seconds || 60)
  cooldownLeft.value = total
  if (cooldownTimer) clearInterval(cooldownTimer)
  cooldownTimer = setInterval(() => {
    cooldownLeft.value -= 1
    if (cooldownLeft.value <= 0) {
      cooldownLeft.value = 0
      clearInterval(cooldownTimer)
      cooldownTimer = null
    }
  }, 1000)
}

const goLogin = () => {
  router.push('/login')
}

const refreshCaptcha = async () => {
  captchaLoading.value = true
  try {
    const res = await axios.get('/api/v1/auth/captcha')
    requestForm.captchaId = String(res?.data?.data?.captcha_id || '')
    requestForm.captchaQuestion = String(res?.data?.data?.question || '')
    requestForm.captchaAnswer = ''
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

const submitRequest = async () => {
  const email = String(requestForm.email || '').trim()
  if (!isValidEmail(email)) {
    ElNotification({ title: 'Error', message: '邮箱格式不正确', type: 'error' })
    return
  }

  const captchaId = String(requestForm.captchaId || '').trim()
  const captchaAnswer = String(requestForm.captchaAnswer || '').trim()
  if (!captchaId || !captchaAnswer) {
    ElNotification({ title: 'Error', message: '请完成验证码', type: 'error' })
    return
  }

  submitting.value = true
  try {
    const res = await axios.post('/api/v1/auth/password/reset/request', {
      email,
      captcha_id: captchaId,
      captcha_answer: captchaAnswer,
    })
    sent.value = true
    ElNotification({ title: 'Success', message: res?.data?.message || '请求已提交', type: 'success' })
    startCooldown(res?.data?.data?.cooldown_seconds || 60)
    await refreshCaptcha()
  } catch (err) {
    ElNotification({
      title: 'Error',
      message: err.response?.data?.message || err.message || '发送失败',
      type: 'error',
    })
    await refreshCaptcha()
  } finally {
    submitting.value = false
  }
}

const submitReset = async () => {
  const password = String(resetForm.password || '')
  const password2 = String(resetForm.password2 || '')
  if (!password || password.length < 6) {
    ElNotification({ title: 'Error', message: '密码长度至少 6 位', type: 'error' })
    return
  }
  if (password !== password2) {
    ElNotification({ title: 'Error', message: '两次密码不一致', type: 'error' })
    return
  }

  submitting.value = true
  try {
    const res = await axios.post('/api/v1/auth/password/reset/confirm', {
      token: token.value,
      new_password: password,
    })
    ElNotification({ title: 'Success', message: res?.data?.message || '密码已重置', type: 'success' })
    await router.push('/login')
  } catch (err) {
    ElNotification({
      title: 'Error',
      message: err.response?.data?.message || err.message || '重置失败',
      type: 'error',
    })
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  if (!hasToken.value) await refreshCaptcha()
})

watch(
  () => hasToken.value,
  async (v) => {
    if (!v) await refreshCaptcha()
  }
)

onUnmounted(() => {
  if (cooldownTimer) clearInterval(cooldownTimer)
  cooldownTimer = null
})
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

.auth-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 12px;
}

.code-row {
  display: flex;
  gap: 10px;
  width: 100%;
}

.captcha-row {
  display: flex;
  gap: 10px;
  width: 100%;
  align-items: center;
}

.captcha-question {
  min-width: 120px;
  padding: 0 10px;
  height: 32px;
  display: flex;
  align-items: center;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  background: #fff;
  color: #111827;
  font-weight: 600;
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
