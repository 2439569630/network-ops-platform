<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">安全设置</div>
      </div>
    </template>

    <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="90px" class="form">
      <el-form-item label="旧密码" prop="oldPassword">
        <el-input v-model="pwdForm.oldPassword" type="password" show-password />
      </el-form-item>
      <el-form-item label="新密码" prop="newPassword">
        <el-input v-model="pwdForm.newPassword" type="password" show-password @input="checkStrength" />
        <div class="pwd-meter">
          <div class="pwd-meter__bar" :class="'lvl-' + pwdStrength"></div>
          <div class="pwd-meter__txt">{{ strengthText }}</div>
        </div>
      </el-form-item>
      <el-form-item label="确认密码" prop="confirmPassword">
        <el-input v-model="pwdForm.confirmPassword" type="password" show-password />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="handleChangePassword" :loading="store.pwdLoading">确认修改</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { computed, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { homeDataStore } from './data';

const router = useRouter();
const store = homeDataStore();

const pwdFormRef = ref(null);
const pwdStrength = ref(0);

const pwdForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
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

const handleChangePassword = async () => {
  if (!pwdFormRef.value) return;
  await pwdFormRef.value.validate(async (valid) => {
    if (!valid) return;
    const ok = await store.changePassword(pwdForm.oldPassword, pwdForm.newPassword);
    if (!ok) return;
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

.form {
  max-width: 720px;
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

