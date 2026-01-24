import { defineStore } from 'pinia';
import { computed, reactive, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

export const homeDataStore = defineStore('homeData', () => {
  const profileLoading = ref(false);
  const summaryLoading = ref(false);
  const ordersLoading = ref(false);
  const historyLoading = ref(false);

  const profileSaving = ref(false);
  const emailSaving = ref(false);
  const pwdLoading = ref(false);
  const securityLoading = ref(false);
  const isEmailNotify = ref(false);

  const now = ref(new Date());
  let clockTimer = null;
  let emailCooldownTimer = null;
  let pollingTimer = null;
  let alertsWs = null;
  let alertsWsReconnectTimer = null;

  const form = reactive({
    id: null,
    username: '',
    nickname: '',
    email: '',
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
  const alertsWsStatus = ref('disconnected');

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

  const displayName = computed(() => form.nickname || form.username || '用户');
  const initials = computed(() => (form.username || 'U').slice(0, 1).toUpperCase());

  const roleCodes = ref([]);
  const isSuper = ref(false);
  const permissions = ref([]);
  const permVer = ref(null);
  const permissionsLoading = ref(false);
  const permissionsLoadedAt = ref(0);

  const PERMS_CACHE_KEY = 'auth:permissions_cache:v1';

  const loadPermsCache = () => {
    try {
      const raw = sessionStorage.getItem(PERMS_CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      const perms = Array.isArray(parsed.permissions) ? parsed.permissions.map(String) : [];
      const loadedAt = Number(parsed.loadedAt || 0);
      const ver = parsed.permVer ?? null;
      if (!Number.isFinite(loadedAt) || loadedAt <= 0) return null;
      return { permissions: perms, loadedAt, permVer: ver };
    } catch {
      return null;
    }
  };

  const savePermsCache = () => {
    try {
      sessionStorage.setItem(
        PERMS_CACHE_KEY,
        JSON.stringify({
          permissions: Array.isArray(permissions.value) ? permissions.value : [],
          permVer: permVer.value ?? null,
          loadedAt: permissionsLoadedAt.value || Date.now(),
        })
      );
    } catch {}
  };

  const clearPermsCache = () => {
    try {
      sessionStorage.removeItem(PERMS_CACHE_KEY);
    } catch {}
  };

  const clearAuthCache = () => {
    permissions.value = [];
    permVer.value = null;
    permissionsLoadedAt.value = 0;
    clearPermsCache();
  };

  const syncAuthFromToken = () => {
    const token = Cookies.get('token');
    if (!token) {
      roleCodes.value = [];
      isSuper.value = false;
      clearAuthCache();
      return;
    }
    try {
      const decoded = jwtDecode(token);
      const roles = Array.isArray(decoded.roles) ? decoded.roles.map(r => String(r).toLowerCase()) : [];
      roleCodes.value = roles;
      isSuper.value = Boolean(decoded.is_super) || roles.includes('admin') || roles.includes('superadmin') || roles.includes('super_admin') || roles.includes('super-admin');

      const tokenPermVer = decoded?.perm_ver ?? null;
      const cached = loadPermsCache();
      if (
        cached &&
        cached.permissions.length > 0 &&
        Date.now() - cached.loadedAt < 5 * 60 * 1000 &&
        tokenPermVer !== null &&
        cached.permVer !== null &&
        String(tokenPermVer) === String(cached.permVer)
      ) {
        permissions.value = cached.permissions;
        permVer.value = cached.permVer;
        permissionsLoadedAt.value = cached.loadedAt;
      }
    } catch {
      roleCodes.value = [];
      isSuper.value = false;
      clearAuthCache();
    }
  };

  const fetchPermissions = async (options = {}) => {
    let force = Boolean(options.force);
    const token = Cookies.get('token');
    if (!token) {
      clearAuthCache();
      return [];
    }

    if (permissionsLoading.value) return permissions.value;

    try {
      const decoded = jwtDecode(token);
      const tokenPermVer = decoded?.perm_ver ?? null;
      if (tokenPermVer !== null && permVer.value !== null && String(tokenPermVer) !== String(permVer.value)) {
        force = true;
      }

      if (!force && permissions.value.length === 0) {
        const cached = loadPermsCache();
        if (
          cached &&
          cached.permissions.length > 0 &&
          Date.now() - cached.loadedAt < 5 * 60 * 1000 &&
          tokenPermVer !== null &&
          cached.permVer !== null &&
          String(tokenPermVer) === String(cached.permVer)
        ) {
          permissions.value = cached.permissions;
          permVer.value = cached.permVer;
          permissionsLoadedAt.value = cached.loadedAt;
          return permissions.value;
        }
      }
    } catch {
      clearAuthCache();
      return [];
    }

    if (!force && permissions.value.length > 0 && Date.now() - permissionsLoadedAt.value < 5 * 60 * 1000) {
      return permissions.value;
    }

    permissionsLoading.value = true;
    try {
      const res = await axios.get('/api/v1/auth/permissions');
      if (res.data?.code === 200) {
        const data = res.data?.data || {};
        const perms = Array.isArray(data.permissions) ? data.permissions.map(String) : [];
        permissions.value = perms;
        permVer.value = data.perm_ver ?? null;
        permissionsLoadedAt.value = Date.now();
        savePermsCache();
        return permissions.value;
      }
      clearAuthCache();
      return [];
    } catch (e) {
      clearAuthCache();
      return [];
    } finally {
      permissionsLoading.value = false;
    }
  };

  const roleName = computed(() => {
    if (isSuper.value) return '超级管理员';
    if (roleCodes.value.includes('yunwei')) return '网络运维';
    return '普通教师/访客';
  });

  const roleTagType = computed(() => {
    if (isSuper.value) return 'danger';
    if (roleCodes.value.includes('yunwei')) return 'warning';
    return 'info';
  });

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

  const completeness = computed(() => {
    const fields = ['nickname', 'email'];
    const filled = fields.filter((f) => !!form[f]).length;
    return Math.floor((filled / fields.length) * 100);
  });

  const startClock = () => {
    if (clockTimer) clearInterval(clockTimer);
    clockTimer = setInterval(() => {
      now.value = new Date();
    }, 1000);
  };

  const stopClock = () => {
    if (!clockTimer) return;
    clearInterval(clockTimer);
    clockTimer = null;
  };

  const stopEmailCooldown = () => {
    if (!emailCooldownTimer) return;
    clearInterval(emailCooldownTimer);
    emailCooldownTimer = null;
  };

  const startEmailCooldown = (seconds) => {
    stopEmailCooldown();
    emailVerify.cooldown = Math.max(0, Number(seconds || 0));
    if (emailVerify.cooldown <= 0) return;
    emailCooldownTimer = setInterval(() => {
      emailVerify.cooldown = Math.max(0, emailVerify.cooldown - 1);
      if (emailVerify.cooldown <= 0) stopEmailCooldown();
    }, 1000);
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

  const resetEmailVerify = () => {
    emailVerify.sent = false;
    emailVerify.email = '';
    emailVerify.expiresAt = 0;
  };

  const fetchProfile = async (options = {}) => {
    profileLoading.value = true;
    try {
      syncAuthFromToken();
      const res = await axios.get('/api/v1/users/profile');
      if (res.data.code === 200) {
        Object.assign(form, res.data.data || {});
        if (options.syncProfileForm) syncProfileForm();
        if (
          form.email &&
          emailVerify.sent &&
          emailVerify.email &&
          String(form.email).trim().toLowerCase() === String(emailVerify.email).trim().toLowerCase()
        ) {
          resetEmailVerify();
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
      return;
    }
  };

  const fetchSummary = async () => {
    summaryLoading.value = true;
    try {
      const res = await axios.get('/api/v1/users/profile/summary');
      if (res.data.code === 200) Object.assign(summary, res.data.data || {});
    } catch (e) {
      console.error('获取统计数据失败:', e);
      return;
    } finally {
      summaryLoading.value = false;
    }
  };

  const fetchRecentOrders = async () => {
    ordersLoading.value = true;
    try {
      // 在个人中心仅展示与我相关的工单（我创建的或指派给我的），即使是管理员也不显示全局工单
      const res = await axios.get('/api/v1/repair-orders/', { 
        params: { page: 1, page_size: 6, scope: 'personal' } 
      });
      if (res.data.code === 200) recentOrders.value = res.data.data?.items || [];
    } catch (e) {
      return;
    } finally {
      ordersLoading.value = false;
    }
  };

  const fetchNotificationHistory = async () => {
    const hasPerm = isSuper.value || (Array.isArray(permissions.value) ? permissions.value : []).includes('sys:notify:history');
    if (!hasPerm) {
      notificationHistory.value = [];
      return;
    }

    historyLoading.value = true;
    try {
      const res = await axios.get('/api/v1/notifications/history');
      if (res.data.code === 200) {
        const items = Array.isArray(res.data.data) ? res.data.data : [];
        notificationHistory.value = items.slice(0, 6);
      }
    } catch (e) {
      return;
    } finally {
      historyLoading.value = false;
    }
  };

  const stopAlertsRealtime = () => {
    try {
      if (alertsWs) alertsWs.close();
    } catch {}
    alertsWs = null;
    if (alertsWsReconnectTimer) {
      clearTimeout(alertsWsReconnectTimer);
      alertsWsReconnectTimer = null;
    }
    alertsWsStatus.value = 'disconnected';
  };

  const startAlertsRealtime = async () => {
    const hasPerm = isSuper.value || (Array.isArray(permissions.value) ? permissions.value : []).includes('sys:notify:history');
    if (!hasPerm) {
      stopAlertsRealtime();
      return;
    }
    const token = Cookies.get('token') || '';
    if (!token) {
      stopAlertsRealtime();
      return;
    }
    if (alertsWs && (alertsWsStatus.value === 'connected' || alertsWsStatus.value === 'connecting')) return;

    stopAlertsRealtime();
    alertsWsStatus.value = 'connecting';

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${window.location.host}/api/v1/notifications/ws/system-alerts?token=${encodeURIComponent(token)}`;

    const mapToHistoryItem = (p) => {
      const time = String((p && (p.time || p.created_at)) || '').trim();
      const title = String((p && (p.source || p.device_name || p.deviceName)) || '系统告警').trim();
      const content = String((p && (p.description || p.content || p.message)) || '').trim();
      const level = String((p && p.level) || '').trim();
      return {
        id: p && p.id,
        created_at: time || new Date().toISOString(),
        title,
        content,
        level,
        raw: p || null,
      };
    };

    const pushItems = (items) => {
      const list = Array.isArray(items) ? items : [];
      const mapped = list.map(mapToHistoryItem).filter((x) => x && x.content);
      const seen = new Set();
      const merged = [...mapped, ...(Array.isArray(notificationHistory.value) ? notificationHistory.value : [])].filter((it) => {
        const key = String(it.id || '') || `${it.created_at}::${it.title}::${it.content}`;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
      });
      notificationHistory.value = merged.slice(0, 6);
    };

    alertsWs = new WebSocket(url);
    alertsWs.onopen = () => {
      alertsWsStatus.value = 'connected';
    };
    alertsWs.onclose = () => {
      alertsWsStatus.value = 'disconnected';
      alertsWs = null;
      if (alertsWsReconnectTimer) clearTimeout(alertsWsReconnectTimer);
      alertsWsReconnectTimer = setTimeout(() => {
        startAlertsRealtime();
      }, 3000);
    };
    alertsWs.onerror = () => {
      alertsWsStatus.value = 'disconnected';
    };
    alertsWs.onmessage = (evt) => {
      try {
        const msg = JSON.parse(evt.data);
        if (msg && msg.type === 'init') {
          pushItems(msg.data);
        } else if (msg && msg.type === 'alert') {
          pushItems([msg.data]);
        }
      } catch {}
    };
  };

  const refreshAll = async (options = {}) => {
    const activePage = String(options.activePage || 'overview');
    await Promise.all([
      fetchProfile({ syncProfileForm: activePage !== 'profile' }),
      fetchSummary(),
      fetchRecentOrders(),
      fetchNotificationHistory(),
      fetchEmailVerifyPending()
    ]);
  };

  const stopPolling = () => {
    if (!pollingTimer) return;
    clearInterval(pollingTimer);
    pollingTimer = null;
  };

  const startPolling = (getActivePage) => {
    stopPolling();
    const readActivePage = () => {
      if (typeof getActivePage === 'function') return String(getActivePage() || 'overview');
      return String(getActivePage || 'overview');
    };

    refreshAll({ activePage: readActivePage() });
    pollingTimer = setInterval(() => {
      refreshAll({ activePage: readActivePage() });
    }, 30000);
  };

  const saveProfile = async (nickname) => {
    profileSaving.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/update', { nickname });
      if (res.data.code === 200) {
        ElMessage.success('保存成功');
        await fetchProfile({ syncProfileForm: true });
        return true;
      }
      ElMessage.error(res.data.message || '保存失败');
      return false;
    } catch (e) {
      ElMessage.error('保存失败');
      return false;
    } finally {
      profileSaving.value = false;
    }
  };

  const applyVerifyMeta = (email, data) => {
    const minutes = Number(data?.expires_in_minutes || 15);
    emailVerify.sent = true;
    emailVerify.email = String(email || '').trim();
    emailVerify.expiresAt = now.value.getTime() + Math.max(1, minutes) * 60 * 1000;
    startEmailCooldown(data?.cooldown_seconds || 60);
  };

  const unlockEmailVerify = () => {
    if (emailVerify.email) emailForm.email = emailVerify.email;
    resetEmailVerify();
  };

  const requestEmailVerify = async (email) => {
    emailSaving.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/email/request', { email });
      if (res.data.code === 200) {
        applyVerifyMeta(email, res.data.data);
        ElMessage.success(res.data.message || '验证邮件已发送');
        return true;
      }
      ElMessage.error(res.data.message || '发送失败');
      return false;
    } catch (e) {
      ElMessage.error(e.response?.data?.message || '发送失败');
      return false;
    } finally {
      emailSaving.value = false;
    }
  };

  const changePassword = async (oldPassword, newPassword) => {
    pwdLoading.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/update', {
        old_password: oldPassword,
        new_password: newPassword
      });
      if (res.data.code === 200) {
        ElMessage.success('密码修改成功，请重新登录');
        return true;
      }
      ElMessage.error(res.data.message || '修改失败');
      return false;
    } catch (e) {
      ElMessage.error('修改失败');
      return false;
    } finally {
      pwdLoading.value = false;
    }
  };

  const fetchSecuritySettings = async () => {
    securityLoading.value = true;
    try {
      const res = await axios.get('/api/v1/auth/users/me/security');
      if (res.data.code === 200) {
        isEmailNotify.value = !!res.data.data.is_email_notify;
      }
    } catch (e) {
      console.error('Failed to fetch security settings:', e);
    } finally {
      securityLoading.value = false;
    }
  };

  const updateSecuritySettings = async (enabled) => {
    securityLoading.value = true;
    try {
      const res = await axios.put('/api/v1/auth/users/me/security', { is_email_notify: enabled });
      if (res.data.code === 200) {
        isEmailNotify.value = enabled;
        ElMessage.success('设置已更新');
        return true;
      }
      ElMessage.error(res.data.message || '更新失败');
      // Revert change if failed
      await fetchSecuritySettings();
      return false;
    } catch (e) {
      ElMessage.error('更新失败');
      await fetchSecuritySettings();
      return false;
    } finally {
      securityLoading.value = false;
    }
  };

  return {
    profileLoading,
    summaryLoading,
    ordersLoading,
    historyLoading,
    profileSaving,
    emailSaving,
    pwdLoading,
    securityLoading,
    isEmailNotify,
    now,
    form,
    summary,
    recentOrders,
    notificationHistory,
    alertsWsStatus,
    profileForm,
    emailForm,
    emailVerify,
    emailVerifyActive,
    emailVerifyExpired,
    emailVerifyRemainText,
    displayName,
    initials,
    roleCodes,
    isSuper,
    permissions,
    permVer,
    permissionsLoading,
    roleName,
    roleTagType,
    nowText,
    greeting,
    completeness,
    startClock,
    stopClock,
    stopEmailCooldown,
    startPolling,
    stopPolling,
    syncAuthFromToken,
    clearAuthCache,
    fetchPermissions,
    syncProfileForm,
    syncEmailForm,
    fetchProfile,
    fetchEmailVerifyPending,
    fetchSummary,
    fetchRecentOrders,
    fetchNotificationHistory,
    refreshAll,
    startAlertsRealtime,
    stopAlertsRealtime,
    saveProfile,
    unlockEmailVerify,
    requestEmailVerify,
    changePassword,
    fetchSecuritySettings,
    updateSecuritySettings
  };
});
