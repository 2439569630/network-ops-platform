<template>
  <div class="auth-page">
    <div class="auth-brand">
      <h1>网络设备自动化运维平台</h1>
    </div>

    <el-card class="auth-card" shadow="never">
      <div class="auth-header">
        <div class="auth-title">注册</div>
        <div class="auth-subtitle">创建账号后需管理员审核</div>
      </div>

      <el-form :model="form" label-position="top" @keyup.enter="submitRegister">
        <el-form-item label="账号">
          <el-input v-model="form.username" placeholder="请输入账号" :prefix-icon="User" />
        </el-form-item>

        <el-form-item label="昵称">
          <el-input v-model="form.nickname" placeholder="可选" :prefix-icon="UserFilled" />
        </el-form-item>

        <el-form-item label="邮箱">
          <el-input v-model="form.email" placeholder="可选" :prefix-icon="Message" />
        </el-form-item>

        <el-form-item label="密码">
          <el-input v-model="form.password" type="password" show-password placeholder="至少 6 位" :prefix-icon="Lock" />
        </el-form-item>

        <el-form-item label="确认密码">
          <el-input v-model="form.password2" type="password" show-password placeholder="再次输入密码" :prefix-icon="Lock" />
        </el-form-item>
      </el-form>

      <div class="auth-actions">
        <el-button @click="goLogin">返回登录</el-button>
        <el-button type="primary" :loading="loading" @click="submitRegister">注册</el-button>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import axios from '@/axios/axios'
import { ElNotification } from 'element-plus'
import { User, Lock, Message, UserFilled } from '@element-plus/icons-vue'

const router = useRouter()
const loading = ref(false)

const form = reactive({
  username: '',
  nickname: '',
  email: '',
  password: '',
  password2: '',
})

const goLogin = () => {
  router.push('/login')
}

const submitRegister = async () => {
  const username = String(form.username || '').trim()
  const nickname = String(form.nickname || '').trim()
  const email = String(form.email || '').trim()
  const password = String(form.password || '')
  const password2 = String(form.password2 || '')

  if (!username || !password) {
    ElNotification({ title: 'Error', message: '账号或密码不能为空', type: 'error' })
    return
  }
  if (password.length < 6) {
    ElNotification({ title: 'Error', message: '密码长度至少 6 位', type: 'error' })
    return
  }
  if (password !== password2) {
    ElNotification({ title: 'Error', message: '两次密码不一致', type: 'error' })
    return
  }

  loading.value = true
  try {
    const res = await axios.post('/api/v1/auth/register', {
      username,
      password,
      nickname: nickname || null,
      email: email || null,
    })
    ElNotification({
      title: 'Success',
      message: res.data?.message || '注册成功',
      type: 'success',
    })
    router.push({ path: '/login', query: { username } })
  } catch (err) {
    ElNotification({
      title: 'Error',
      message: err.response?.data?.message || err.message || '注册失败',
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
  margin-top: 4px;
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
