<template>
  <div class="user-edit-page" :class="{ 'is-mobile': isMobile }">
    <div class="page-header">
      <div class="header-main">
        <div class="header-title">
          <div class="title">编辑用户</div>
          <div class="subtitle">修改用户基本资料、审核状态与角色信息</div>
        </div>
        <div class="header-actions">
          <el-button @click="goBack">返回</el-button>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="main-card" v-loading="loading">
      <template v-if="formReady">
        <el-form
          ref="formRef"
          :model="form"
          :rules="rules"
          label-position="top"
          class="edit-form"
          @submit.prevent
        >
          <el-form-item label="头像">
            <div class="avatar-row">
              <el-avatar :size="72" :src="detail.avatar_url || ''" class="avatar">
                <span>{{ initials }}</span>
              </el-avatar>
              <el-upload
                v-if="canManageUsers"
                :show-file-list="false"
                accept="image/*"
                :before-upload="beforeAvatarUpload"
                :http-request="handleAvatarUpload"
                :disabled="avatarUploading || loading || saving"
              >
                <el-button type="primary" :loading="avatarUploading">上传头像</el-button>
              </el-upload>
              <div class="avatar-tip">{{ canManageUsers ? '支持 jpg/png/gif/webp/bmp，最大 5MB' : '当前账号仅可查看，不能修改头像' }}</div>
            </div>
          </el-form-item>

          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <el-form-item label="用户名">
                <el-input :model-value="detail.username || ''" disabled />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :md="12">
              <el-form-item label="用户 ID">
                <el-input :model-value="String(detail.id || '')" disabled />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <el-form-item label="昵称" prop="nickname">
                <el-input v-model="form.nickname" maxlength="20" show-word-limit placeholder="请输入昵称" :disabled="!canManageUsers" />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :md="12">
              <el-form-item label="邮箱" prop="email">
                <el-input v-model="form.email" placeholder="请输入邮箱地址" :disabled="!canManageUsers" />
              </el-form-item>
            </el-col>
          </el-row>

          <el-row :gutter="16">
            <el-col :xs="24" :md="12">
              <el-form-item label="账号状态">
                <el-switch
                  v-model="form.is_approved"
                  inline-prompt
                  active-text="启用"
                  inactive-text="封禁"
                  :disabled="!canManageUsers"
                />
              </el-form-item>
            </el-col>
            <el-col :xs="24" :md="12">
              <el-form-item label="邮件通知">
                <el-switch
                  v-model="form.is_email_notify"
                  inline-prompt
                  active-text="开启"
                  inactive-text="关闭"
                  :disabled="!canManageUsers"
                />
              </el-form-item>
            </el-col>
          </el-row>

          <el-form-item v-if="canManageUsers" label="角色" prop="role_ids">
            <el-select v-model="form.role_ids" multiple filterable placeholder="请选择角色" style="width: 100%">
              <el-option
                v-for="role in roleOptions"
                :key="role.id"
                :label="`${role.name}${role.code ? ` (${role.code})` : ''}`"
                :value="role.id"
              />
            </el-select>
          </el-form-item>

          <el-form-item v-else label="角色">
            <div class="readonly-roles">
              <el-tag v-for="role in (detail.roles || [])" :key="role.id" effect="plain">
                {{ role.name }}<span v-if="role.code"> ({{ role.code }})</span>
              </el-tag>
              <span v-if="!detail.roles || detail.roles.length === 0" class="empty-text">暂无角色</span>
            </div>
          </el-form-item>

          <div class="meta-list">
            <div class="meta-item">
              <span class="meta-label">创建时间</span>
              <span class="meta-value">{{ formatTime(detail.created_at) }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">更新时间</span>
              <span class="meta-value">{{ formatTime(detail.updated_at) }}</span>
            </div>
          </div>

          <div class="form-actions">
            <el-button @click="goBack">取消</el-button>
            <el-button v-if="canManageUsers" type="primary" :loading="saving" @click="handleSubmit">保存修改</el-button>
          </div>
        </el-form>
      </template>

      <el-empty v-else-if="!loading" description="未找到用户信息" />
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import axios from '@/axios/axios';
import { homeDataStore } from '@/components/home/home/data';

const route = useRoute();
const router = useRouter();
const authStore = homeDataStore();

const loading = ref(false);
const saving = ref(false);
const avatarUploading = ref(false);
const formRef = ref(null);
const roleOptions = ref([]);
const detail = ref({});
const isMobile = ref(window.innerWidth < 768);
const canManageUsers = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:user:manage')));

const userId = computed(() => {
  const raw = Number(route.params.id);
  return Number.isFinite(raw) && raw > 0 ? raw : null;
});

const form = reactive({
  nickname: '',
  email: '',
  is_email_notify: false,
  is_approved: true,
  role_ids: [],
});

const rules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 2, max: 20, message: '昵称长度需在 2 到 20 个字符之间', trigger: 'blur' },
  ],
  email: [
    {
      validator: (_rule, value, callback) => {
        const raw = String(value || '').trim();
        if (!raw) {
          callback();
          return;
        }
        const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(raw);
        callback(ok ? undefined : new Error('邮箱格式不正确'));
      },
      trigger: 'blur',
    },
  ],
  role_ids: [
    {
      validator: (_rule, value, callback) => {
        if (Array.isArray(value) && value.length > 0) {
          callback();
          return;
        }
        callback(new Error('请至少选择一个角色'));
      },
      trigger: 'change',
    },
  ],
};

const formReady = computed(() => Boolean(detail.value && detail.value.id));
const initials = computed(() => {
  const raw = String(detail.value?.nickname || detail.value?.username || '?').trim();
  return (raw.charAt(0) || '?').toUpperCase();
});

const handleResize = () => {
  isMobile.value = window.innerWidth < 768;
};

const formatTime = (value) => {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mi = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${yyyy}-${mm}-${dd} ${hh}:${mi}:${ss}`;
};

const applyDetail = (data) => {
  const next = data || {};
  detail.value = next;
  form.nickname = String(next.nickname || '').trim();
  form.email = String(next.email || '').trim();
  form.is_email_notify = Boolean(next.is_email_notify);
  form.is_approved = Boolean(next.is_approved);
  form.role_ids = Array.isArray(next.roles) ? next.roles.map((r) => Number(r.id)).filter((id) => Number.isFinite(id)) : [];
};

const fetchRoles = async () => {
  if (!canManageUsers.value) {
    roleOptions.value = [];
    return;
  }
  try {
    const res = await axios.get('/api/v1/users/role-options');
    if (res.data?.code === 200) {
      roleOptions.value = Array.isArray(res.data.data) ? res.data.data : [];
    } else {
      ElMessage.error(res.data?.message || '获取角色列表失败');
    }
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '获取角色列表失败');
  }
};

const fetchDetail = async () => {
  if (!userId.value) {
    ElMessage.error('用户 ID 无效');
    return;
  }
  loading.value = true;
  try {
    const res = await axios.get(`/api/v1/users/${userId.value}`);
    if (res.data?.code === 200 && res.data?.data) {
      applyDetail(res.data.data);
      return;
    }
    ElMessage.error(res.data?.message || '获取用户详情失败');
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '获取用户详情失败');
  } finally {
    loading.value = false;
  }
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
  if (!userId.value) return;
  try {
    avatarUploading.value = true;
    const formData = new FormData();
    formData.append('file', options.file);
    const res = await axios.post(`/api/v1/users/${userId.value}/avatar/upload`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    if (res.data?.code === 200) {
      detail.value = {
        ...detail.value,
        avatar_url: res.data?.data?.avatar_url || detail.value?.avatar_url || '',
      };
      ElMessage.success('头像已更新');
      await fetchDetail();
      options?.onSuccess?.(res.data, options.file);
      return;
    }
    const msg = res.data?.message || '上传失败';
    ElMessage.error(msg);
    options?.onError?.(new Error(msg));
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || '上传失败');
    options?.onError?.(e);
  } finally {
    avatarUploading.value = false;
  }
};

const goBack = () => {
  router.push('/user/user-manage');
};

const handleSubmit = async () => {
  if (!userId.value || !formRef.value) return;
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    saving.value = true;
    try {
      const payload = {
        nickname: String(form.nickname || '').trim(),
        email: String(form.email || '').trim() || null,
        is_email_notify: Boolean(form.is_email_notify),
        is_approved: Boolean(form.is_approved),
        role_ids: Array.isArray(form.role_ids) ? form.role_ids : [],
      };
      const res = await axios.put(`/api/v1/users/${userId.value}`, payload);
      if (res.data?.code === 200) {
        ElMessage.success('保存成功');
        await fetchDetail();
        return;
      }
      ElMessage.error(res.data?.message || '保存失败');
    } catch (e) {
      ElMessage.error(e?.response?.data?.message || '保存失败');
    } finally {
      saving.value = false;
    }
  });
};

onMounted(async () => {
  window.addEventListener('resize', handleResize);
  authStore.syncAuthFromToken();
  await authStore.fetchPermissions({ force: true });
  await Promise.all([fetchRoles(), fetchDetail()]);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
});
</script>

<style scoped>
.user-edit-page {
  padding: 24px;
  min-height: 100vh;
  background: #f5f7fa;
}

.user-edit-page.is-mobile {
  padding: 16px;
}

.page-header {
  margin-bottom: 16px;
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.header-title .title {
  font-size: 24px;
  font-weight: 600;
  color: #1f2f3d;
}

.header-title .subtitle {
  margin-top: 6px;
  color: #909399;
  font-size: 14px;
}

.main-card {
  border-radius: 12px;
}

.edit-form {
  max-width: 960px;
}

.avatar-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.avatar {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.18), rgba(103, 194, 58, 0.16));
  color: #111827;
  font-weight: 700;
}

.avatar-tip {
  color: #909399;
  font-size: 12px;
}

.readonly-roles {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.empty-text {
  color: #909399;
}

.meta-list {
  display: flex;
  flex-wrap: wrap;
  gap: 24px;
  padding-top: 8px;
  color: #606266;
}

.meta-item {
  display: flex;
  gap: 8px;
}

.meta-label {
  color: #909399;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 24px;
}

.is-mobile .header-main {
  flex-direction: column;
  align-items: stretch;
}

.is-mobile .form-actions {
  justify-content: stretch;
}
</style>
