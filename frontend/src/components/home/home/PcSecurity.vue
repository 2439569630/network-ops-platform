<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">安全设置</div>
      </div>
    </template>

    <div class="section-title">邮箱设置</div>
    <div class="section-content">
      <div class="notify-item">
        <div class="notify-text">
          <div class="notify-label">接收邮箱通知</div>
          <div class="notify-desc">关闭后，将不再接收邮箱类通知，包括告警邮件与登录提醒邮件</div>
        </div>
        <el-switch
          v-model="store.isEmailNotify"
          :loading="store.securityLoading"
          @change="handleEmailNotifyChange"
        />
      </div>
      <div class="notify-item">
        <div class="notify-text">
          <div class="notify-label">登录邮件提醒</div>
          <div class="notify-desc">开启后，检测到登录环境变化时会向绑定邮箱发送提醒邮件，需同时开启接收邮箱通知</div>
        </div>
        <el-switch
          v-model="store.isLoginEmailNotify"
          :loading="store.securityLoading"
          @change="handleLoginNotifyChange"
        />
      </div>
    </div>

    <el-divider />

    <div class="section-title">修改密码</div>
    <div class="section-tip">
      <span v-if="store.securityEmail">已绑定安全邮箱：{{ maskedSecurityEmail }}</span>
      <span v-else>修改密码前需先绑定邮箱，当前账号尚未绑定安全邮箱。</span>
    </div>
    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px" class="form">
      <el-form-item label="旧密码" prop="oldPassword">
        <el-input v-model="pwdForm.oldPassword" type="password" show-password :disabled="!hasSecurityEmail" />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input v-model="pwdForm.newPassword" type="password" show-password @input="checkStrength" :disabled="!hasSecurityEmail" />
        <div class="pwd-meter">
          <div class="pwd-meter__bar" :class="'lvl-' + pwdStrength"></div>
          <div class="pwd-meter__txt">{{ strengthText }}</div>
        </div>
      </el-form-item>
      <el-form-item label="确认密码" prop="confirmPassword">
        <el-input v-model="pwdForm.confirmPassword" type="password" show-password :disabled="!hasSecurityEmail" />
      </el-form-item>
      <el-form-item label="邮箱验证码" prop="emailCode">
        <div class="code-row">
          <el-input v-model="pwdForm.emailCode" placeholder="请输入邮箱验证码" :disabled="!hasSecurityEmail" />
          <el-button
            type="primary"
            plain
            :loading="store.pwdCodeLoading"
            :disabled="!hasSecurityEmail || store.pwdCodeCooldown > 0"
            @click="handleSendPasswordCode"
          >
            {{ store.pwdCodeCooldown > 0 ? `${store.pwdCodeCooldown}s 后重发` : '发送验证码' }}
          </el-button>
        </div>
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleChangePassword" :loading="store.pwdLoading" :disabled="!hasSecurityEmail">确认修改</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { computed, reactive, ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { useRouter } from 'vue-router';
import { homeDataStore } from './data';

const router = useRouter();
const store = homeDataStore();

onMounted(() => {
  store.fetchSecuritySettings();
});

const handleEmailNotifyChange = (val) => {
  store.updateSecuritySettings({ is_email_notify: val });
};

const handleLoginNotifyChange = (val) => {
  store.updateSecuritySettings({ is_login_email_notify: val });
};

const pwdFormRef = ref(null);
const pwdStrength = ref(0);

const pwdForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: '',
  emailCode: ''
});

const hasSecurityEmail = computed(() => Boolean(String(store.securityEmail || '').trim()));
const maskedSecurityEmail = computed(() => {
  const raw = String(store.securityEmail || '').trim();
  if (!raw.includes('@')) return raw;
  const [local, domain] = raw.split('@', 2);
  if (local.length <= 2) return `${local.slice(0, 1)}*@${domain}`;
  return `${local.slice(0, 2)}${'*'.repeat(Math.max(1, local.length - 2))}@${domain}`;
});

const strengthText = computed(() => {
  const map = ['弱', '中', '强', '极强'];
  return map[Math.min(pwdStrength.value, 3)];
});

const pwdRules = {
  oldPassword: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
  newPassword: [
    { required: true, message: '请输入新密码', trigger: 'blur' },
    { min: 6, message: '密码长度不能少于6位', trigger: 'blur' }
  ],
  confirmPassword: [
    { required: true, message: '请确认密码', trigger: 'blur' },
    {
      validator: (rule, value, cb) => {
        if (value !== pwdForm.newPassword) cb(new Error('两次密码不一致'));
        else cb();
      },
      trigger: 'blur'
    }
  ],
  emailCode: [
    { required: true, message: '请输入邮箱验证码', trigger: 'blur' },
    { min: 6, max: 6, message: '验证码为6位数字', trigger: 'blur' }
  ]
};

const checkStrength = (value) => {
  const v = String(value || '');
  let s = 0;
  if (v.length > 5) s++;
  if (/[A-Z]/.test(v)) s++;
  if (/[0-9]/.test(v)) s++;
  if (/[^A-Za-z0-9]/.test(v)) s++;
  pwdStrength.value = s > 0 ? s - 1 : 0;
};

const handleSendPasswordCode = async () => {
  if (!hasSecurityEmail.value) {
    ElMessage.warning('请先绑定邮箱后再修改密码');
    return;
  }
  await store.requestPasswordChangeCode();
};

const handleChangePassword = async () => {
  if (!pwdFormRef.value) return;
  await pwdFormRef.value.validate(async (valid) => {
    if (!valid) return;
    const ok = await store.changePassword(pwdForm.oldPassword, pwdForm.newPassword, pwdForm.emailCode);
    if (!ok) return;
    pwdForm.oldPassword = '';
    pwdForm.newPassword = '';
    pwdForm.confirmPassword = '';
    pwdForm.emailCode = '';
    setTimeout(() => router.push('/Login'), 1200);
  });
};
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

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #111827;
  margin-bottom: 16px;
}

.section-content {
  padding: 0 12px;
}

.notify-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.notify-label {
  font-size: 14px;
  color: #374151;
  font-weight: 500;
}

.notify-desc {
  font-size: 13px;
  color: #6b7280;
  margin-top: 2px;
}

.form {
  max-width: 720px;
  margin-top: 24px;
}

.section-tip {
  margin-bottom: 12px;
  color: #6b7280;
  font-size: 13px;
}

.code-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.code-row :deep(.el-input) {
  flex: 1;
}

.pwd-meter {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.pwd-meter__bar {
  flex: 1;
  height: 6px;
  border-radius: 999px;
  background: #eef2f7;
  position: relative;
  overflow: hidden;
}

.pwd-meter__bar::after {
  content: '';
  position: absolute;
  inset: 0;
  transform-origin: left center;
  transform: scaleX(0.25);
  border-radius: 999px;
  background: #f56c6c;
  transition: transform 220ms ease, background 220ms ease;
}

.lvl-0::after {
  transform: scaleX(0.25);
  background: #f56c6c;
}
.lvl-1::after {
  transform: scaleX(0.5);
  background: #e6a23c;
}
.lvl-2::after {
  transform: scaleX(0.75);
  background: #409eff;
}
.lvl-3::after {
  transform: scaleX(1);
  background: #67c23a;
}

.pwd-meter__txt {
  width: 32px;
  text-align: right;
  color: #6b7280;
  font-size: 12px;
}
</style>
