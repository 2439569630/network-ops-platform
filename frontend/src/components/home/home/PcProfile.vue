<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">资料设置</div>
      </div>
    </template>

    <el-form ref="profileFormRef" :model="store.profileForm" :rules="profileRules" label-width="90px" class="form">
      <el-form-item label="昵称" prop="nickname">
        <el-input v-model="store.profileForm.nickname" maxlength="20" show-word-limit />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="saveProfile" :loading="store.profileSaving">保存</el-button>
        <el-button @click="resetProfileForm">重置</el-button>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import { homeDataStore } from './data';

const store = homeDataStore();
const profileFormRef = ref(null);

const profileRules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 2, max: 20, message: '长度在 2 到 20 个字符', trigger: 'blur' }
  ]
};

const saveProfile = async () => {
  if (!profileFormRef.value) return;
  await profileFormRef.value.validate(async (valid) => {
    if (!valid) return;
    await store.saveProfile(store.profileForm.nickname);
  });
};

const resetProfileForm = () => {
  store.syncProfileForm();
  profileFormRef.value?.clearValidate?.();
};

onMounted(() => {
  store.syncProfileForm();
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
</style>

