<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">邮箱设置</div>
      </div>
    </template>

    <div class="hint">
      <div class="hint__title">绑定邮箱</div>
      <div class="hint__desc">邮箱用于接收系统通知与找回密码。需完成邮件验证后才会绑定生效。</div>
    </div>

    <el-form ref="emailFormRef" :model="store.emailForm" :rules="emailRules" label-width="110px" class="form">
      <el-form-item label="当前邮箱">
        <el-input :model-value="store.form.email || '未绑定'" disabled />
      </el-form-item>
      <el-form-item v-if="store.emailVerifyActive" label="待验证邮箱">
        <el-input :model-value="store.emailVerify.email" disabled />
      </el-form-item>
      <el-form-item v-else label="新邮箱" prop="email">
        <el-input v-model="store.emailForm.email" placeholder="name@example.com" />
      </el-form-item>
      <el-form-item v-if="store.emailVerifyActive">
        <el-alert
          type="success"
          show-icon
          :closable="false"
          title="验证邮件已发送"
          :description="`请到邮箱 ${store.emailVerify.email} 点击验证链接完成绑定（剩余有效期 ${store.emailVerifyRemainText}）。验证完成后回到此页稍等片刻，邮箱状态会自动更新。`"
        />
      </el-form-item>
      <el-form-item v-else-if="store.emailVerifyExpired">
        <el-alert
          type="warning"
          show-icon
          :closable="false"
          title="验证链接已过期"
          :description="`上次发送到邮箱 ${store.emailVerify.email} 的验证链接已过期，请重新发送验证邮件。`"
        />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="sendEmailVerify" :loading="store.emailSaving" :disabled="store.emailVerify.cooldown > 0">
          {{
            store.emailVerify.cooldown > 0
              ? `重新发送(${store.emailVerify.cooldown}s)`
              : store.emailVerifyActive || store.emailVerifyExpired
                ? '重新发送验证邮件'
                : '发送验证邮件'
          }}
        </el-button>
        <el-button v-if="store.emailVerifyActive" @click="unlockEmailVerify">更换邮箱</el-button>
        <el-button @click="resetEmailForm">重置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { homeDataStore } from './data';

const store = homeDataStore();
const emailFormRef = ref(null);

const emailRules = {
  email: [
    { required: true, message: '请输入邮箱', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(String(value || ''));
        if (!ok) return cb(new Error('邮箱格式不正确'));
        cb();
      },
      trigger: 'blur'
    }
  ]
};

const resetEmailForm = () => {
  store.syncEmailForm();
  emailFormRef.value?.clearValidate?.();
};

const unlockEmailVerify = () => {
  store.unlockEmailVerify();
  emailFormRef.value?.clearValidate?.();
};

const sendEmailVerify = async () => {
  if (store.emailVerifyActive) {
    const email = String(store.emailVerify.email || '').trim();
    if (!email) return;
    await store.requestEmailVerify(email);
    return;
  }

  if (!emailFormRef.value) return;
  await emailFormRef.value.validate(async (valid) => {
    if (!valid) return;
    const email = String(store.emailForm.email || '').trim();
    await store.requestEmailVerify(email);
  });
};

onMounted(() => {
  store.syncEmailForm();
  store.fetchEmailVerifyPending();
});
</script>

<style scoped>
.card {
  border-radius: 14px;
  border: none;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.06) !important;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  font-weight: 700;
  color: #111827;
}

.form {
  max-width: 720px;
}

.hint {
  padding: 12px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
  margin-bottom: 14px;
}

.hint__title {
  font-weight: 800;
  color: #111827;
}

.hint__desc {
  margin-top: 6px;
  color: #6b7280;
  font-size: 13px;
}
</style>

