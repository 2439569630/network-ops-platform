<template>
  <div class="pc">
    <div class="hero">
      <div class="hero__bg" />
      <div class="hero__inner">
        <div class="hero__top">
          <div class="identity">
            <el-avatar :size="56" class="identity__avatar">
              <span>{{ initials }}</span>
            </el-avatar>
            <div class="identity__meta">
              <div class="identity__title">
                <span class="identity__greet">{{ greeting }}，</span>
                <span class="identity__name">{{ displayName }}</span>
              </div>
              <div class="identity__sub">
                <el-tag :type="roleTagType" effect="dark" round size="small">{{ roleName }}</el-tag>
                <span class="sep" />
                <span>{{ nowText }}</span>
                <span class="sep" />
                <span>注册第 {{ summary.register_days || 1 }} 天</span>
              </div>
            </div>
          </div>

          <div class="hero__actions">
            <el-button @click="refreshAll" :loading="anyLoading">刷新</el-button>
          </div>
        </div>

        <div class="kpi-wrap">
          <div class="kpi-grid" v-loading="summaryLoading">
            <div class="kpi">
              <div class="kpi__label">待处理工单</div>
              <div class="kpi__value">{{ summary.order_open || 0 }}</div>
            </div>
            <div class="kpi">
              <div class="kpi__label">我的工单</div>
              <div class="kpi__value">{{ summary.order_total || 0 }}</div>
            </div>
            <div class="kpi">
              <div class="kpi__label">已完成</div>
              <div class="kpi__value">{{ summary.order_done || 0 }}</div>
            </div>
            <div class="kpi">
              <div class="kpi__label">我创建的设备</div>
              <div class="kpi__value">{{ summary.device_count || 0 }}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="content">
      <el-row :gutter="16">
        <el-col :lg="6" :md="24" :sm="24" :xs="24">
          <el-card class="card nav-card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">个人中心</div>
              </div>
            </template>

            <div class="mini" v-loading="profileLoading">
              <div class="mini__top">
                <el-avatar :size="56" class="mini__avatar">
                  <span>{{ initials }}</span>
                </el-avatar>
                <div class="mini__meta">
                  <div class="mini__name">{{ displayName }}</div>
                  <div class="mini__sub muted">账号：{{ form.username || '-' }}</div>
                  <div class="mini__sub muted">邮箱：{{ form.email || '未绑定' }}</div>
                </div>
              </div>

              <div class="progress-wrap">
                <div class="progress-title">
                  <span>资料完整度</span>
                  <span class="muted">{{ completeness }}%</span>
                </div>
                <el-progress :percentage="completeness" :show-text="false" :color="customColors" />
              </div>
            </div>

            <el-divider />

            <el-menu class="nav" :default-active="activePage" @select="setPage">
              <el-menu-item index="overview">概览</el-menu-item>
              <el-menu-item index="profile">资料设置</el-menu-item>
              <el-menu-item index="email">邮箱设置</el-menu-item>
              <el-menu-item index="security">安全设置</el-menu-item>
              <el-menu-item index="notification">通知策略</el-menu-item>
            </el-menu>
          </el-card>
        </el-col>

        <el-col :lg="18" :md="24" :sm="24" :xs="24">
          <div v-if="activePage === 'overview'">
            <el-card class="card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <div class="card-title">最近工单</div>
                  <div class="card-actions">
                    <el-button link type="primary" @click="fetchRecentOrders" :loading="ordersLoading">刷新</el-button>
                  </div>
                </div>
              </template>

              <el-skeleton v-if="ordersLoading" :rows="5" animated />
              <div v-else>
                <el-empty v-if="recentOrders.length === 0" description="暂无工单" />
                <el-table v-else :data="recentOrders" size="small" style="width: 100%">
                  <el-table-column prop="id" label="ID" width="80" />
                  <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
                  <el-table-column label="状态" width="120">
                    <template #default="{ row }">
                      <el-tag :type="statusTagType(row.status)" effect="light">{{ statusText(row.status) }}</el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column label="创建时间" width="180">
                    <template #default="{ row }">
                      <span class="muted">{{ formatTime(row.created_at) }}</span>
                    </template>
                  </el-table-column>
                </el-table>
              </div>
            </el-card>

            <el-card class="card mt" shadow="hover">
              <template #header>
                <div class="card-header">
                  <div class="card-title">通知动态</div>
                  <div class="card-actions">
                    <el-button link type="primary" @click="fetchNotificationHistory" :loading="historyLoading">刷新</el-button>
                  </div>
                </div>
              </template>

              <el-skeleton v-if="historyLoading" :rows="4" animated />
              <div v-else class="notify-list">
                <el-empty v-if="notificationHistory.length === 0" description="暂无通知" />
                <div v-else class="notify-item" v-for="n in notificationHistory" :key="n.id || n.created_at">
                  <div class="notify-item__time">{{ formatTime(n.created_at) }}</div>
                  <div class="notify-item__main">
                    <div class="notify-item__title">{{ n.title || '系统通知' }}</div>
                    <div class="notify-item__content">{{ n.content || '-' }}</div>
                  </div>
                </div>
              </div>
            </el-card>
          </div>

          <el-card v-else-if="activePage === 'profile'" class="card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">资料设置</div>
              </div>
            </template>

            <el-form ref="profileFormRef" :model="profileForm" :rules="profileRules" label-width="90px" class="form">
              <el-form-item label="昵称" prop="nickname">
                <el-input v-model="profileForm.nickname" maxlength="20" show-word-limit />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="saveProfile" :loading="profileSaving">保存</el-button>
                <el-button @click="resetProfileForm">重置</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card v-else-if="activePage === 'email'" class="card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">邮箱设置</div>
              </div>
            </template>

            <div class="hint">
              <div class="hint__title">绑定邮箱</div>
              <div class="hint__desc">邮箱用于接收系统通知与找回密码。需完成邮件验证后才会绑定生效。</div>
            </div>

            <el-form ref="emailFormRef" :model="emailForm" :rules="emailRules" label-width="110px" class="form">
              <el-form-item label="当前邮箱">
                <el-input :model-value="form.email || '未绑定'" disabled />
              </el-form-item>
              <el-form-item v-if="emailVerifyActive" label="待验证邮箱">
                <el-input :model-value="emailVerify.email" disabled />
              </el-form-item>
              <el-form-item v-else label="新邮箱" prop="email">
                <el-input v-model="emailForm.email" placeholder="name@example.com" />
              </el-form-item>
              <el-form-item v-if="emailVerifyActive">
                <el-alert
                  type="success"
                  show-icon
                  :closable="false"
                  title="验证邮件已发送"
                  :description="`请到邮箱 ${emailVerify.email} 点击验证链接完成绑定（剩余有效期 ${emailVerifyRemainText}）。验证完成后回到此页点击“刷新邮箱”。`"
                />
              </el-form-item>
              <el-form-item v-else-if="emailVerifyExpired">
                <el-alert
                  type="warning"
                  show-icon
                  :closable="false"
                  title="验证链接已过期"
                  :description="`上次发送到邮箱 ${emailVerify.email} 的验证链接已过期，请重新发送验证邮件。`"
                />
              </el-form-item>
              <el-form-item>
                <el-button type="primary" @click="sendEmailVerify" :loading="emailSaving" :disabled="emailVerify.cooldown > 0">
                  {{
                    emailVerify.cooldown > 0
                      ? `重新发送(${emailVerify.cooldown}s)`
                      : emailVerifyActive || emailVerifyExpired
                        ? '重新发送验证邮件'
                        : '发送验证邮件'
                  }}
                </el-button>
                <el-button v-if="emailVerifyActive" @click="unlockEmailVerify">更换邮箱</el-button>
                <el-button @click="fetchProfile" :loading="profileLoading">刷新邮箱</el-button>
                <el-button @click="resetEmailForm">重置</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card v-else-if="activePage === 'security'" class="card" shadow="hover">
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
                <el-button type="primary" @click="handleChangePassword" :loading="pwdLoading">确认修改</el-button>
              </el-form-item>
            </el-form>
          </el-card>

          <el-card v-else class="card" shadow="hover">
            <template #header>
              <div class="card-header">
                <div class="card-title">通知策略</div>
              </div>
            </template>

            <div class="hint">
              <div class="hint__title">统一配置</div>
              <div class="hint__desc">通知策略由管理员统一配置，普通用户不可修改。</div>
            </div>

            <el-form label-width="150px" label-position="left" v-loading="notifyLoading" class="form">
              <el-form-item label="启用邮件通知">
                <el-switch :model-value="!!notifyConfig.enable_email" disabled />
              </el-form-item>
              <el-form-item label="使用全局邮箱配置">
                <el-switch :model-value="!!notifyConfig.use_global_email" disabled />
              </el-form-item>
              <el-form-item label="启用 PushPlus">
                <el-switch :model-value="!!notifyConfig.enable_pushplus" disabled />
              </el-form-item>
              <el-form-item label="启用 HTTP 回调">
                <el-switch :model-value="!!notifyConfig.enable_http" disabled />
              </el-form-item>
              <el-form-item>
                <el-button @click="fetchNotifyConfig" :loading="notifyLoading">刷新</el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount, computed } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';

const router = useRouter();
const route = useRoute();

const profileLoading = ref(false);
const summaryLoading = ref(false);
const ordersLoading = ref(false);
const historyLoading = ref(false);
const notifyLoading = ref(false);

const profileSaving = ref(false);
const emailSaving = ref(false);
const pwdLoading = ref(false);

const profileFormRef = ref(null);
const emailFormRef = ref(null);
const pwdFormRef = ref(null);

const form = reactive({
  id: null,
  username: '',
  nickname: '',
  email: '',
  permission_level: 2,
  created_at: ''
});

const summary = reactive({
  register_days: 1,
  device_count: 0,
  order_total: 0,
  order_open: 0,
  order_done: 0
});

const recentOrders = ref([]);
const notificationHistory = ref([]);

const notifyConfig = reactive({
  enable_email: false,
  use_global_email: false,
  email_config: {},
  enable_pushplus: false,
  pushplus_token: '',
  enable_http: false,
  http_url: ''
});

const profileForm = reactive({
  nickname: ''
});

const emailForm = reactive({
  email: ''
});

const emailVerify = reactive({
  sent: false,
  email: '',
  cooldown: 0,
  expiresAt: 0
});

const pwdStrength = ref(0);
const pwdForm = reactive({
  oldPassword: '',
  newPassword: '',
  confirmPassword: ''
});

const anyLoading = computed(
  () =>
    profileLoading.value ||
    summaryLoading.value ||
    ordersLoading.value ||
    historyLoading.value ||
    notifyLoading.value
);

const activePage = computed(() => {
  const p = String(route.query.page || 'overview');
  const allow = ['overview', 'profile', 'email', 'security', 'notification'];
  return allow.includes(p) ? p : 'overview';
});

const setPage = (key) => {
  router.replace({ query: { ...route.query, page: key } });
  if (key === 'profile') syncProfileForm();
  if (key === 'email') {
    syncEmailForm();
    fetchEmailVerifyPending();
  }
};

const displayName = computed(() => form.nickname || form.username || '用户');
const initials = computed(() => (form.username || 'U').slice(0, 1).toUpperCase());

const roleName = computed(() => {
  switch (Number(form.permission_level)) {
    case 0:
      return '超级管理员';
    case 1:
      return '网络运维';
    case 2:
      return '普通教师/访客';
    default:
      return '未知';
  }
});

const roleTagType = computed(() => {
  switch (Number(form.permission_level)) {
    case 0:
      return 'danger';
    case 1:
      return 'warning';
    case 2:
      return 'info';
    default:
      return '';
  }
});

const now = ref(new Date());
let timer = null;

const nowText = computed(() => {
  const d = now.value;
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  return `${y}-${m}-${day} ${hh}:${mm}`;
});

const greeting = computed(() => {
  const h = now.value.getHours();
  if (h < 6) return '凌晨好';
  if (h < 12) return '早上好';
  if (h < 18) return '下午好';
  return '晚上好';
});

const emailVerifyRemaining = computed(() => {
  const exp = Number(emailVerify.expiresAt || 0);
  if (!exp) return 0;
  const diffMs = exp - now.value.getTime();
  return Math.max(0, Math.floor(diffMs / 1000));
});

const emailVerifyActive = computed(() => emailVerify.sent && emailVerifyRemaining.value > 0);

const emailVerifyExpired = computed(() => emailVerify.sent && emailVerifyRemaining.value === 0);

const emailVerifyRemainText = computed(() => {
  const s = emailVerifyRemaining.value;
  const mm = String(Math.floor(s / 60)).padStart(2, '0');
  const ss = String(s % 60).padStart(2, '0');
  return `${mm}:${ss}`;
});

const completeness = computed(() => {
  const fields = ['nickname', 'email'];
  const filled = fields.filter((f) => !!form[f]).length;
  return Math.floor((filled / fields.length) * 100);
});

const customColors = [
  { color: '#f56c6c', percentage: 25 },
  { color: '#e6a23c', percentage: 50 },
  { color: '#409eff', percentage: 75 },
  { color: '#67c23a', percentage: 100 }
];

const strengthText = computed(() => {
  const map = ['弱', '中', '强', '极强'];
  return map[Math.min(pwdStrength.value, 3)];
});

const profileRules = {
  nickname: [
    { required: true, message: '请输入昵称', trigger: 'blur' },
    { min: 2, max: 20, message: '长度在 2 到 20 个字符', trigger: 'blur' }
  ]
};

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

const syncProfileForm = () => {
  profileForm.nickname = form.nickname || '';
};

const syncEmailForm = () => {
  if (emailVerifyActive.value) return;
  if (emailVerify.sent) {
    emailForm.email = emailVerify.email || '';
    return;
  }
  emailForm.email = '';
};

const resetProfileForm = () => {
  syncProfileForm();
  profileFormRef.value?.clearValidate?.();
};

const resetEmailForm = () => {
  syncEmailForm();
  emailFormRef.value?.clearValidate?.();
};

const formatTime = (value) => {
  if (!value) return '-';
  const s = String(value);
  if (s.includes('T')) return s.replace('T', ' ').slice(0, 19);
  return s.slice(0, 19);
};

const statusText = (s) => {
  const v = String(s || '');
  if (v === 'pending') return '待处理';
  if (v === 'processing') return '处理中';
  if (v === 'need_info') return '需补充';
  if (v === 'completed') return '已完成';
  if (v === 'closed') return '已关闭';
  if (v === 'cancelled') return '已取消';
  return v || '-';
};

const statusTagType = (s) => {
  const v = String(s || '');
  if (v === 'pending') return 'warning';
  if (v === 'processing') return 'primary';
  if (v === 'need_info') return 'danger';
  if (v === 'completed' || v === 'closed') return 'success';
  if (v === 'cancelled') return 'info';
  return '';
};

const fetchProfile = async () => {
  profileLoading.value = true;
  try {
    const res = await axios.get('/api/v1/users/profile');
    if (res.data.code === 200) {
      Object.assign(form, res.data.data || {});
      syncProfileForm();
      if (
        form.email &&
        emailVerify.sent &&
        emailVerify.email &&
        String(form.email).trim().toLowerCase() === String(emailVerify.email).trim().toLowerCase()
      ) {
        emailVerify.sent = false;
        emailVerify.email = '';
        emailVerify.expiresAt = 0;
      }
    }
  } catch (e) {
    ElMessage.error('获取用户信息失败');
  } finally {
    profileLoading.value = false;
  }
};

const fetchEmailVerifyPending = async () => {
  try {
    const res = await axios.get('/api/v1/users/profile/email/pending');
    if (res.data.code !== 200) return;
    const data = res.data.data;
    if (!data || !data.email || !data.expires_at) return;

    const exp = new Date(String(data.expires_at)).getTime();
    if (!Number.isFinite(exp) || exp <= now.value.getTime()) return;

    emailVerify.sent = true;
    emailVerify.email = String(data.email || '').trim();
    emailVerify.expiresAt = exp;
  } catch (e) {
    // ignore
  }
};

const fetchSummary = async () => {
  summaryLoading.value = true;
  try {
    const res = await axios.get('/api/v1/users/profile/summary');
    if (res.data.code === 200) Object.assign(summary, res.data.data || {});
  } catch (e) {
    // ignore
  } finally {
    summaryLoading.value = false;
  }
};

const fetchRecentOrders = async () => {
  ordersLoading.value = true;
  try {
    const res = await axios.get('/api/v1/repair-orders/', { params: { page: 1, page_size: 6 } });
    if (res.data.code === 200) recentOrders.value = res.data.data?.items || [];
  } catch (e) {
    // ignore
  } finally {
    ordersLoading.value = false;
  }
};

const fetchNotificationHistory = async () => {
  historyLoading.value = true;
  try {
    const res = await axios.get('/api/v1/notifications/history');
    if (res.data.code === 200) {
      const items = Array.isArray(res.data.data) ? res.data.data : [];
      notificationHistory.value = items.slice(0, 6);
    }
  } catch (e) {
    // ignore
  } finally {
    historyLoading.value = false;
  }
};

const fetchNotifyConfig = async () => {
  notifyLoading.value = true;
  try {
    const res = await axios.get('/api/v1/notifications/config');
    if (res.data.code === 200) Object.assign(notifyConfig, res.data.data || {});
  } catch (e) {
    // ignore
  } finally {
    notifyLoading.value = false;
  }
};

const saveProfile = async () => {
  if (!profileFormRef.value) return;
  await profileFormRef.value.validate(async (valid) => {
    if (!valid) return;
    profileSaving.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/update', { nickname: profileForm.nickname });
      if (res.data.code === 200) {
        ElMessage.success('保存成功');
        await fetchProfile();
      } else {
        ElMessage.error(res.data.message || '保存失败');
      }
    } catch (e) {
      ElMessage.error('保存失败');
    } finally {
      profileSaving.value = false;
    }
  });
};

let emailCooldownTimer = null;

const startEmailCooldown = (seconds) => {
  if (emailCooldownTimer) clearInterval(emailCooldownTimer);
  emailVerify.cooldown = Math.max(0, Number(seconds || 0));
  if (emailVerify.cooldown <= 0) return;
  emailCooldownTimer = setInterval(() => {
    emailVerify.cooldown = Math.max(0, emailVerify.cooldown - 1);
    if (emailVerify.cooldown <= 0 && emailCooldownTimer) {
      clearInterval(emailCooldownTimer);
      emailCooldownTimer = null;
    }
  }, 1000);
};

const unlockEmailVerify = () => {
  if (emailVerify.email) emailForm.email = emailVerify.email;
  emailVerify.sent = false;
  emailVerify.email = '';
  emailVerify.expiresAt = 0;
  emailFormRef.value?.clearValidate?.();
};

const applyVerifyMeta = (email, data) => {
  const minutes = Number(data?.expires_in_minutes || 15);
  emailVerify.sent = true;
  emailVerify.email = String(email || '').trim();
  emailVerify.expiresAt = now.value.getTime() + Math.max(1, minutes) * 60 * 1000;
  startEmailCooldown(data?.cooldown_seconds || 60);
};

const sendEmailVerify = async () => {
  const send = async (email) => {
    emailSaving.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/email/request', { email });
      if (res.data.code === 200) {
        applyVerifyMeta(email, res.data.data);
        ElMessage.success(res.data.message || '验证邮件已发送');
      } else {
        ElMessage.error(res.data.message || '发送失败');
      }
    } catch (e) {
      ElMessage.error(e.response?.data?.message || '发送失败');
    } finally {
      emailSaving.value = false;
    }
  };

  if (emailVerifyActive.value) {
    const email = String(emailVerify.email || '').trim();
    if (!email) return;
    await send(email);
    return;
  }

  if (!emailFormRef.value) return;
  await emailFormRef.value.validate(async (valid) => {
    if (!valid) return;
    const email = String(emailForm.email || '').trim();
    await send(email);
  });
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
    pwdLoading.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/update', {
        old_password: pwdForm.oldPassword,
        new_password: pwdForm.newPassword
      });
      if (res.data.code === 200) {
        ElMessage.success('密码修改成功，请重新登录');
        setTimeout(() => router.push('/Login'), 1200);
      } else {
        ElMessage.error(res.data.message || '修改失败');
      }
    } catch (e) {
      ElMessage.error('修改失败');
    } finally {
      pwdLoading.value = false;
    }
  });
};

const refreshAll = async () => {
  await Promise.all([
    fetchProfile(),
    fetchSummary(),
    fetchRecentOrders(),
    fetchNotificationHistory(),
    fetchNotifyConfig(),
    fetchEmailVerifyPending()
  ]);
};

onMounted(() => {
  timer = setInterval(() => {
    now.value = new Date();
  }, 1000);
  refreshAll();
});

onBeforeUnmount(() => {
  if (timer) clearInterval(timer);
  if (emailCooldownTimer) clearInterval(emailCooldownTimer);
});
</script>

<style scoped>
.pc {
  min-height: 100%;
  background: radial-gradient(1200px 600px at 20% 0%, rgba(64, 158, 255, 0.20), transparent 60%),
    radial-gradient(900px 500px at 90% 20%, rgba(103, 194, 58, 0.16), transparent 55%),
    #f6f8fb;
}

.hero {
  position: relative;
  padding: 28px 18px 18px;
}

.hero__bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #1f6feb 0%, #409eff 35%, #34c759 100%);
  border-radius: 0 0 22px 22px;
  opacity: 0.95;
}

.hero__inner {
  position: relative;
  max-width: 1180px;
  margin: 0 auto;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.28);
  backdrop-filter: blur(14px);
}

.hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.identity__avatar {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  font-weight: 700;
  border: 1px solid rgba(255, 255, 255, 0.25);
}

.identity__meta {
  min-width: 0;
}

.identity__title {
  display: flex;
  align-items: baseline;
  gap: 6px;
  color: #fff;
  font-weight: 700;
  letter-spacing: 0.2px;
  font-size: 20px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.identity__greet {
  opacity: 0.95;
}

.identity__name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.identity__sub {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 13px;
  flex-wrap: wrap;
}

.sep {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.75);
  display: inline-block;
}

.hero__actions {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.kpi-wrap {
  margin-top: 14px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.24);
  padding: 14px 14px 12px;
}

.kpi__label {
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
}

.kpi__value {
  margin-top: 6px;
  color: #fff;
  font-weight: 800;
  font-size: 26px;
  line-height: 1.1;
}

.content {
  max-width: 1180px;
  margin: -18px auto 0;
  padding: 0 18px 28px;
}

.card {
  border-radius: 14px;
  border: none;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.06) !important;
}

.nav-card :deep(.el-card__body) {
  padding-top: 10px;
}

.mt {
  margin-top: 16px;
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

.card-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.muted {
  color: #6b7280;
}

.mini {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mini__top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mini__avatar {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.18), rgba(103, 194, 58, 0.16));
  border: 1px solid rgba(15, 23, 42, 0.06);
  color: #111827;
  font-weight: 800;
}

.mini__meta {
  min-width: 0;
}

.mini__name {
  font-weight: 800;
  color: #111827;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini__sub {
  margin-top: 4px;
  font-size: 12px;
}

.progress-wrap {
  padding: 12px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.progress-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 8px;
}

.nav {
  border-right: none;
}

.notify-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.notify-item {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 12px;
  padding: 12px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.notify-item__time {
  color: #6b7280;
  font-size: 12px;
}

.notify-item__title {
  font-weight: 700;
  color: #111827;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notify-item__content {
  margin-top: 4px;
  color: #4b5563;
  font-size: 13px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
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

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 720px) {
  .hero__top {
    flex-direction: column;
    align-items: flex-start;
  }
  .hero__actions {
    justify-content: flex-start;
  }
  .notify-item {
    grid-template-columns: 1fr;
  }
}
</style>
