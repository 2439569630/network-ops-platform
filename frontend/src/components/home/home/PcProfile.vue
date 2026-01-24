<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">资料设置</div>
      </div>
    </template>

    <el-form ref="profileFormRef" :model="store.profileForm" :rules="profileRules" label-width="90px" class="form">
      <el-form-item label="头像">
        <div class="avatar-row">
          <el-avatar :size="56" class="avatar" :src="store.form.avatar_url || ''">
            <span>{{ store.initials }}</span>
          </el-avatar>
          <el-upload
            :show-file-list="false"
            accept="image/*"
            :before-upload="beforeAvatarUpload"
            :http-request="handleAvatarUpload"
            :disabled="avatarUploading || store.profileLoading"
          >
            <el-button :loading="avatarUploading" type="primary">上传头像</el-button>
          </el-upload>
          <div class="avatar-tip muted">支持 jpg/png/gif/webp/bmp，最大 5MB</div>
        </div>
      </el-form-item>
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
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';

const store = homeDataStore();
const profileFormRef = ref(null);
const avatarUploading = ref(false);

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

const beforeAvatarUpload = (file) => {
  const maxBytes = 5 * 1024 * 1024;
  const type = String(file?.type || '');
  if (!type.startsWith('image/')) {
    ElMessage.error('仅支持图片文件');
    return false;
  }
  const size = Number(file?.size || 0);
  if (size > maxBytes) {
    ElMessage.error('头像图片过大(最大 5MB)');
    return false;
  }
  return true;
};

const handleAvatarUpload = async (options) => {
  try {
    avatarUploading.value = true;
    const formData = new FormData();
    formData.append('file', options.file);
    const res = await axios.post('/api/v1/users/avatar/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    });
    if (res.data.code === 200) {
      ElMessage.success('头像已更新');
      await store.fetchProfile({ syncProfileForm: true });
      options?.onSuccess?.(res.data, options.file);
      return;
    }
    const msg = res.data.message || '上传失败';
    ElMessage.error(msg);
    options?.onError?.(new Error(msg));
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '上传失败');
    options?.onError?.(e);
  } finally {
    avatarUploading.value = false;
  }
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

.avatar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.avatar {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.18), rgba(103, 194, 58, 0.16));
  border: 1px solid rgba(15, 23, 42, 0.06);
  color: #111827;
  font-weight: 800;
}

.avatar-tip {
  font-size: 12px;
}

.muted {
  color: #6b7280;
}
</style>
