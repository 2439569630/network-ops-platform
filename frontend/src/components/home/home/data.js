import { defineStore } from 'pinia';
import { computed, reactive, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';

export const homeDataStore = defineStore('homeData', () => {
  const profileLoading = ref(false);
  const summaryLoading = ref(false);
  const ordersLoading = ref(false);
  const historyLoading = ref(false);

  const profileSaving = ref(false);
  const emailSaving = ref(false);
  const pwdLoading = ref(false);
  const pwdCodeLoading = ref(false);
  const securityLoading = ref(false);
  const isEmailNotify = ref(false);
  const isLoginEmailNotify = ref(false);
  const securityEmail = ref('');
  const pwdCodeCooldown = ref(0);

  const now = ref(new Date());
  let clockTimer = null;
  let emailCooldownTimer = null;
  let pwdCodeCooldownTimer = null;
  let pollingTimer = null;
  let alertsWs = null;
  let alertsWsReconnectTimer = null;

  const form = reactive({
    id: null,
    username: '',
    nickname: '',
    email: '',
    avatar_url: '',
    roles: [],
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
  const SUPER_ROLE_CODES = new Set(['superadmin', 'super_admin', 'super-admin']);
  const normalizeRoleCodes = (roles) => (
    Array.isArray(roles)
      ? roles.map(r => String(r || '').trim().toLowerCase()).filter(Boolean)
      : []
  );
  const resolveSuperFromPayload = (payload = {}) => {
    const roles = normalizeRoleCodes(payload?.roles);
    const roleCode = String(payload?.roleCode || payload?.role_code || '').trim().toLowerCase();
    const roleKey = String(payload?.roleKey || payload?.role_key || '').trim().toLowerCase();
    const userType = String(payload?.user_type || payload?.userType || '').trim().toLowerCase();
    return Boolean(
      payload?.is_super === true ||
      payload?.is_super_admin === true ||
      payload?.isSuper === true ||
      payload?.isSuperAdmin === true ||
      roles.some(code => SUPER_ROLE_CODES.has(code)) ||
      SUPER_ROLE_CODES.has(roleCode) ||
      SUPER_ROLE_CODES.has(roleKey) ||
      userType === 'super'
    );
  };
  const isSuperAdmin = (payload) => {
    if (payload && typeof payload === 'object') return resolveSuperFromPayload(payload);
    return resolveSuperFromPayload({ is_super: isSuper.value, roles: roleCodes.value });
  };
  const sessionUserId = ref(null);
  const sessionUsername = ref('');
  const sessionPermVer = ref(null);
  const sessionAuthVer = ref(null);
  const sessionLoadedAt = ref(0);
  const permissions = ref([]);
  const permVer = ref(null);
  const permissionsLoading = ref(false);
  const permissionsLoadedAt = ref(0);
  let permissionsPromise = null;

  const PERMS_CACHE_KEY = 'auth:permissions_cache:v1';
  const SESSION_CACHE_KEY = 'auth:session_cache:v1';

  const loadSessionCache = () => {
    try {
      const raw = sessionStorage.getItem(SESSION_CACHE_KEY);
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return null;
      const loadedAt = Number(parsed.loadedAt || 0);
      if (!Number.isFinite(loadedAt) || loadedAt <= 0) return null;
      return {
        id: parsed.id ?? null,
        username: String(parsed.username || ''),
        roles: normalizeRoleCodes(parsed.roles),
        isSuper: resolveSuperFromPayload({
          is_super: parsed.is_super,
          is_super_admin: parsed.is_super_admin,
          isSuper: parsed.isSuper,
          isSuperAdmin: parsed.isSuperAdmin,
          roleCode: parsed.roleCode || parsed.role_code,
          roleKey: parsed.roleKey || parsed.role_key,
          user_type: parsed.user_type,
          roles: parsed.roles,
        }),
        permVer: parsed.perm_ver ?? null,
        authVer: parsed.auth_ver ?? null,
        loadedAt,
      };
    } catch {
      return null;
    }
  };

  const saveSessionCache = () => {
    try {
      sessionStorage.setItem(
        SESSION_CACHE_KEY,
        JSON.stringify({
          id: sessionUserId.value ?? null,
          username: sessionUsername.value || '',
          roles: Array.isArray(roleCodes.value) ? roleCodes.value : [],
          is_super: Boolean(isSuper.value || false),
          perm_ver: sessionPermVer.value ?? null,
          auth_ver: sessionAuthVer.value ?? null,
          loadedAt: sessionLoadedAt.value || Date.now(),
        })
      );
    } catch {}
  };

  const clearSessionCache = () => {
    try {
      sessionStorage.removeItem(SESSION_CACHE_KEY);
    } catch {}
  };

  const applySession = (data) => {
    const roles = normalizeRoleCodes(data?.roles);
    roleCodes.value = roles;
    isSuper.value = isSuperAdmin(data);
    sessionUserId.value = data?.id ?? null;
    sessionUsername.value = String(data?.username || '');
    sessionPermVer.value = data?.perm_ver ?? null;
    sessionAuthVer.value = data?.auth_ver ?? null;
    sessionLoadedAt.value = Date.now();
    saveSessionCache();
  };

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
    const cached = loadSessionCache();
    if (!cached) {
      roleCodes.value = [];
      isSuper.value = false;
      sessionUserId.value = null;
      sessionUsername.value = '';
      sessionPermVer.value = null;
      sessionAuthVer.value = null;
      sessionLoadedAt.value = 0;
      clearAuthCache();
      return;
    }
    roleCodes.value = cached.roles;
    isSuper.value = isSuperAdmin(cached);
    sessionUserId.value = cached.id ?? null;
    sessionUsername.value = cached.username || '';
    sessionPermVer.value = cached.permVer ?? null;
    sessionAuthVer.value = cached.authVer ?? null;
    sessionLoadedAt.value = cached.loadedAt || 0;

    const cachedPerms = loadPermsCache();
    const tokenPermVer = cached.permVer ?? null;
    if (
      cachedPerms &&
      cachedPerms.permissions.length > 0 &&
      Date.now() - cachedPerms.loadedAt < 5 * 60 * 1000 &&
      (
        (tokenPermVer !== null && cachedPerms.permVer !== null && String(tokenPermVer) === String(cachedPerms.permVer)) ||
        tokenPermVer === null
      )
    ) {
      permissions.value = cachedPerms.permissions;
      permVer.value = cachedPerms.permVer;
      permissionsLoadedAt.value = cachedPerms.loadedAt;
    }
  };

  let sessionPromise = null;
  const ensureSession = async (options = {}) => {
    const force = Boolean(options.force);
    const cache = loadSessionCache();
    if (!force && cache && Date.now() - cache.loadedAt < 5 * 60 * 1000) {
      syncAuthFromToken();
      return cache;
    }
    if (sessionPromise && !force) return sessionPromise;
    sessionPromise = (async () => {
      try {
        const res = await axios.get('/api/v1/auth/me');
        if (res?.data?.code === 200) {
          applySession(res.data?.data || {});
          return loadSessionCache();
        }
        roleCodes.value = [];
        isSuper.value = false;
        sessionUserId.value = null;
        sessionUsername.value = '';
        sessionPermVer.value = null;
        sessionAuthVer.value = null;
        sessionLoadedAt.value = 0;
        clearSessionCache();
        clearAuthCache();
        return null;
      } catch (e) {
        roleCodes.value = [];
        isSuper.value = false;
        sessionUserId.value = null;
        sessionUsername.value = '';
        sessionPermVer.value = null;
        sessionAuthVer.value = null;
        sessionLoadedAt.value = 0;
        clearSessionCache();
        clearAuthCache();
        return null;
      } finally {
        sessionPromise = null;
      }
    })();
    return await sessionPromise;
  };

  const fetchPermissions = async (options = {}) => {
    let force = Boolean(options.force);
    const session = await ensureSession();
    if (!session) {
      clearAuthCache();
      return [];
    }

    if (permissionsPromise && !force) return permissionsPromise;
    if (permissionsPromise && force) {
      try {
        await permissionsPromise;
      } catch {}
    }

    try {
      const tokenPermVer = session?.permVer ?? null;
      if (tokenPermVer !== null && permVer.value !== null && String(tokenPermVer) !== String(permVer.value)) {
        force = true;
      }

      if (!force && permissions.value.length === 0) {
        const cached = loadPermsCache();
        if (
          cached &&
          cached.permissions.length > 0 &&
          Date.now() - cached.loadedAt < 5 * 60 * 1000 &&
          (
            (tokenPermVer !== null && cached.permVer !== null && String(tokenPermVer) === String(cached.permVer)) ||
            tokenPermVer === null
          )
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
    permissionsPromise = (async () => {
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
    })();
    try {
      return await permissionsPromise;
    } finally {
      permissionsPromise = null;
    }
  };

  const resolveRoleTagType = (code) => {
    const normalized = String(code || '').trim().toLowerCase();
    if (SUPER_ROLE_CODES.has(normalized)) return 'danger';
    if (normalized.includes('yunwei')) return 'warning';
    return 'info';
  };

  const roleBadges = computed(() => {
    const roles = Array.isArray(form.roles) ? form.roles : [];
    if (roles.length > 0) {
      return roles
        .filter(item => item && (item.name || item.code))
        .map(item => ({
          key: String(item.id ?? item.code ?? item.name),
          label: String(item.name || item.code || '未命名角色'),
          type: resolveRoleTagType(item.code),
        }));
    }
    if (isSuper.value) {
      return [{ key: 'superadmin', label: '超级管理员', type: 'danger' }];
    }
    if (roleCodes.value.includes('yunwei')) {
      return [{ key: 'yunwei', label: '网络运维', type: 'warning' }];
    }
    return [{ key: 'default', label: '普通教师/访客', type: 'info' }];
  });

  const roleName = computed(() => roleBadges.value.map(item => item.label).join(' / '));

  const roleTagType = computed(() => {
    const first = roleBadges.value[0];
    return first?.type || 'info';
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
    const session = await ensureSession();
    if (!session) {
      stopAlertsRealtime();
      return;
    }
    if (alertsWs && (alertsWsStatus.value === 'connected' || alertsWsStatus.value === 'connecting')) return;

    stopAlertsRealtime();
    alertsWsStatus.value = 'connecting';

    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const url = `${proto}://${window.location.host}/api/v1/notifications/ws/system-alerts`;

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

  const stopPwdCodeCooldown = () => {
    if (pwdCodeCooldownTimer) {
      clearInterval(pwdCodeCooldownTimer);
      pwdCodeCooldownTimer = null;
    }
  };

  const startPwdCodeCooldown = (seconds) => {
    stopPwdCodeCooldown();
    pwdCodeCooldown.value = Math.max(0, Number(seconds || 0));
    if (pwdCodeCooldown.value <= 0) return;
    pwdCodeCooldownTimer = setInterval(() => {
      pwdCodeCooldown.value = Math.max(0, pwdCodeCooldown.value - 1);
      if (pwdCodeCooldown.value <= 0) stopPwdCodeCooldown();
    }, 1000);
  };

  const requestPasswordChangeCode = async () => {
    pwdCodeLoading.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/password/code/request');
      if (res.data.code === 200) {
        startPwdCodeCooldown(res.data.data?.cooldown_seconds || 60);
        ElMessage.success(res.data.message || '验证码已发送');
        return true;
      }
      ElMessage.error(res.data.message || '发送失败');
      return false;
    } catch (e) {
      ElMessage.error(e.response?.data?.message || '发送失败');
      return false;
    } finally {
      pwdCodeLoading.value = false;
    }
  };

  const changePassword = async (oldPassword, newPassword, emailCode) => {
    pwdLoading.value = true;
    try {
      const res = await axios.post('/api/v1/users/profile/update', {
        old_password: oldPassword,
        new_password: newPassword,
        email_code: emailCode
      });
      if (res.data.code === 200) {
        ElMessage.success('密码修改成功，请重新登录');
        stopPwdCodeCooldown();
        pwdCodeCooldown.value = 0;
        return true;
      }
      ElMessage.error(res.data.message || '修改失败');
      return false;
    } catch (e) {
      ElMessage.error(e.response?.data?.message || '修改失败');
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
        securityEmail.value = String(res.data.data.email || '');
        isEmailNotify.value = !!res.data.data.is_email_notify;
        isLoginEmailNotify.value = !!res.data.data.is_login_email_notify;
      }
    } catch (e) {
      console.error('Failed to fetch security settings:', e);
    } finally {
      securityLoading.value = false;
    }
  };

  const updateSecuritySettings = async (payload) => {
    securityLoading.value = true;
    try {
      const res = await axios.put('/api/v1/auth/users/me/security', payload);
      if (res.data.code === 200) {
        if (Object.prototype.hasOwnProperty.call(res.data.data || {}, 'is_email_notify')) {
          isEmailNotify.value = !!res.data.data.is_email_notify;
        }
        if (Object.prototype.hasOwnProperty.call(res.data.data || {}, 'is_login_email_notify')) {
          isLoginEmailNotify.value = !!res.data.data.is_login_email_notify;
        }
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

  const resetForLogout = () => {
    stopPolling();
    stopAlertsRealtime();
    stopClock();
    stopEmailCooldown();

    profileLoading.value = false;
    summaryLoading.value = false;
    ordersLoading.value = false;
    historyLoading.value = false;
    profileSaving.value = false;
    emailSaving.value = false;
    pwdLoading.value = false;
    securityLoading.value = false;
    isEmailNotify.value = false;
    isLoginEmailNotify.value = false;

    now.value = new Date();
    Object.assign(form, {
      id: null,
      username: '',
      nickname: '',
      email: '',
      avatar_url: '',
          roles: [],
      created_at: ''
    });
    Object.assign(summary, {
      register_days: 1,
      device_count: 0,
      order_total: 0,
      order_open: 0,
      order_done: 0
    });
    recentOrders.value = [];
    notificationHistory.value = [];
    alertsWsStatus.value = 'disconnected';
    profileForm.nickname = '';
    emailForm.email = '';
    resetEmailVerify();
    securityEmail.value = '';
    stopPwdCodeCooldown();
    pwdCodeCooldown.value = 0;

    roleCodes.value = [];
    isSuper.value = false;
    sessionUserId.value = null;
    sessionUsername.value = '';
    sessionPermVer.value = null;
    sessionAuthVer.value = null;
    sessionLoadedAt.value = 0;
    clearSessionCache();
    clearAuthCache();
  };

  return {
    profileLoading,
    summaryLoading,
    ordersLoading,
    historyLoading,
    profileSaving,
    emailSaving,
    pwdLoading,
    pwdCodeLoading,
    securityLoading,
    isEmailNotify,
    isLoginEmailNotify,
    securityEmail,
    pwdCodeCooldown,
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
    isSuperAdmin,
    permissions,
    permVer,
    permissionsLoading,
    roleBadges,
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
    ensureSession,
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
    requestPasswordChangeCode,
    changePassword,
    fetchSecuritySettings,
    updateSecuritySettings,
    resetForLogout
  };
});
