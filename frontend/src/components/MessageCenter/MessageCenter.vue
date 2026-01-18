<template>
  <div class="mc-container">
    <div class="mc-header">
      <div class="page-title">
        <el-icon class="mr-2"><Bell /></el-icon>
        <span>消息中心</span>
        <el-tooltip content="设备通知、站内消息与推送设置" placement="right">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
    </div>

    <div class="mc-content">
      <div class="mc-topbar">
        <div ref="tabSwitcherRef" class="tab-switcher">
          <div
            v-for="tab in visibleTabs"
            :key="tab.name"
            class="tab-item"
            :ref="(el) => setTabRef(tab.name, el)"
            :class="{ active: activeTab === tab.name }"
            @click="activeTab = tab.name"
          >
            <el-icon><component :is="tab.icon" /></el-icon> {{ tab.label }}
          </div>
          <div class="tab-indicator" :style="indicatorStyle"></div>
        </div>

        <div class="topbar-right" v-if="activeTab === 'alerts'">
        </div>
      </div>

      <div class="mc-body">
        <div v-show="activeTab === 'site'" class="tab-body">
          <div class="toolbar">
            <div class="toolbar__row">
              <el-space wrap alignment="center">
                <el-input v-model="siteMessagesKeyword" size="small" clearable placeholder="搜索标题/内容/发件人" style="width: 260px" />
                <el-switch v-model="siteMessagesUnreadOnly" inline-prompt active-text="未读" inactive-text="全部" @change="loadSiteMessages" />
              </el-space>
              <div class="toolbar__right">
                <el-button v-if="canSendSiteMessages" size="small" type="primary" @click="goPublishPage">发布通知</el-button>
              </div>
            </div>
          </div>

          <div class="tab-main">
            <div
              class="site-list"
            >
              <div v-loading="siteLoading" class="site-list__inner">
                <div v-if="filteredSiteMessages.length === 0 && !siteLoading" class="site-empty">
                  <el-empty description="暂无站内消息" />
                </div>

                <div v-for="m in filteredSiteMessages" :key="m.id" class="site-item">
                  <el-card
                    shadow="never"
                    class="site-card"
                    :class="m.is_read ? 'site-card--read' : 'site-card--unread'"
                    @click="openSiteMessageDetail(m)"
                  >
                    <div class="site-card__header">
                      <div class="site-card__title">{{ m.title }}</div>
                      <div class="site-card__tags">
                        <el-tag :type="m.is_read ? 'info' : 'warning'" effect="plain" size="small">
                          {{ m.is_read ? '已阅' : '未阅' }}
                        </el-tag>
                      </div>
                    </div>
                    <div class="site-card__content">
                      {{ buildSiteMessageSnippet(m.content) }}
                    </div>
                    <div class="site-card__meta">
                      <span class="muted">{{ m.sender_name || m.source || '-' }}</span>
                      <span class="dot">·</span>
                      <span class="muted">{{ formatDateTime(m.created_at) }}</span>
                    </div>
                  </el-card>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div v-show="activeTab === 'notifications'" class="tab-body">
          <el-row :gutter="12" class="stats-row">
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ notificationStats.total }}</div>
                <div class="stat-label">通知总数（最近100条）</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value stat-value--danger">{{ notificationStats.error }}</div>
                <div class="stat-label">错误</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value stat-value--warning">{{ notificationStats.warning }}</div>
                <div class="stat-label">告警</div>
              </el-card>
            </el-col>
          </el-row>

          <div class="toolbar">
            <el-space wrap alignment="center">
              <el-select v-model="notificationsLevel" size="small" style="width: 140px">
                <el-option label="全部级别" value="all" />
                <el-option label="error" value="error" />
                <el-option label="warning" value="warning" />
                <el-option label="info" value="info" />
              </el-select>
              <el-input v-model="notificationsKeyword" size="small" clearable placeholder="搜索设备/内容" style="width: 260px" />
              <el-button size="small" :loading="loading" @click="fetchNotifications">刷新</el-button>
            </el-space>
          </div>

          <div class="tab-main">
            <el-table :data="filteredNotifications" stripe v-loading="loading" height="100%" class="table table--fill" empty-text="暂无通知">
              <el-table-column prop="created_at" label="时间" width="180">
                <template #default="scope">
                  {{ formatDateTime(scope.row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column prop="level" label="级别" width="110">
                <template #default="scope">
                  <el-tag :type="getLevelType(scope.row.level)" effect="light">{{ String(scope.row.level || '').toLowerCase() }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="device_name" label="设备" width="180" show-overflow-tooltip />
              <el-table-column prop="message" label="内容" min-width="260" show-overflow-tooltip />
            </el-table>
          </div>
        </div>

        <div v-show="activeTab === 'settings'" class="tab-body">
          <el-row :gutter="12">
            <el-col :xs="24" :lg="12">
              <el-card shadow="never" class="settings-card" v-loading="configLoading">
                <template #header>
                  <div class="settings-card__header">
                    <div class="settings-card__title">邮箱通知</div>
                  </div>
                </template>

                <el-form label-position="top">
                  <el-form-item label="开启邮箱通知">
                    <el-switch v-model="config.enable_email" :disabled="!canEditConfig" />
                  </el-form-item>

                  <template v-if="config.enable_email">
                    <el-row :gutter="12">
                      <el-col :span="12">
                        <el-form-item label="SMTP 服务器">
                          <el-input v-model="config.email_config.host" placeholder="smtp.example.com" :disabled="!canEditConfig" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="端口">
                          <el-input v-model="config.email_config.port" placeholder="465" :disabled="!canEditConfig" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="用户名">
                          <el-input v-model="config.email_config.username" placeholder="user@example.com" :disabled="!canEditConfig" />
                        </el-form-item>
                      </el-col>
                      <el-col :span="12">
                        <el-form-item label="授权码/密码">
                          <el-input v-model="config.email_config.password" type="password" show-password :disabled="!canEditConfig" />
                        </el-form-item>
                      </el-col>
                    </el-row>

                    <el-form-item label="测试接收邮箱">
                      <el-row :gutter="12">
                        <el-col :xs="24" :sm="16">
                          <el-input v-model="testEmailTarget" placeholder="输入邮箱地址" :disabled="!canEditConfig" />
                        </el-col>
                        <el-col :xs="24" :sm="8">
                          <el-button style="width: 100%" @click="handleTest('email')" :disabled="!canTest">发送测试</el-button>
                        </el-col>
                      </el-row>
                    </el-form-item>
                  </template>
                </el-form>
              </el-card>
            </el-col>

            <el-col :xs="24" :lg="12">
              <el-card shadow="never" class="settings-card" v-loading="configLoading">
                <template #header>
                  <div class="settings-card__header">
                    <div class="settings-card__title">推送渠道</div>
                  </div>
                </template>

                <el-form label-position="top">
                  <el-form-item label="开启 PushPlus">
                    <el-switch v-model="config.enable_pushplus" :disabled="!canEditConfig" />
                  </el-form-item>
                  <el-form-item label="PushPlus Token" v-if="config.enable_pushplus">
                    <el-row :gutter="12">
                      <el-col :xs="24" :sm="16">
                        <el-input v-model="config.pushplus_token" placeholder="PushPlus Token" :disabled="!canEditConfig" />
                      </el-col>
                      <el-col :xs="24" :sm="8">
                        <el-button style="width: 100%" @click="handleTest('pushplus')" :disabled="!canTest">测试</el-button>
                      </el-col>
                    </el-row>
                  </el-form-item>

                  <el-form-item label="开启 HTTP 回调">
                    <el-switch v-model="config.enable_http" :disabled="!canEditConfig" />
                  </el-form-item>
                  <el-form-item label="Webhook URL" v-if="config.enable_http">
                    <el-row :gutter="12">
                      <el-col :xs="24" :sm="16">
                        <el-input v-model="config.http_url" placeholder="http://your-api.com/callback" :disabled="!canEditConfig" />
                      </el-col>
                      <el-col :xs="24" :sm="8">
                        <el-button style="width: 100%" @click="handleTest('http')" :disabled="!canTest">测试</el-button>
                      </el-col>
                    </el-row>
                  </el-form-item>

                  <el-button type="primary" style="width: 100%" @click="saveConfig" :disabled="!canEditConfig">保存配置</el-button>
                </el-form>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, reactive, computed, nextTick, watch } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import { useRoute, useRouter } from 'vue-router';
import { homeDataStore } from '@/components/home/home/data';
import { messageCenterDataStore } from '@/components/MessageCenter/date';
import { Bell, InfoFilled, WarningFilled, Message, Setting } from '@element-plus/icons-vue';

const activeTab = ref('site');
const notifications = ref([]);
const loading = ref(false);
const configLoading = ref(false);
const store = homeDataStore();
const msgStore = messageCenterDataStore();
const router = useRouter();
const route = useRoute();
const siteMessages = computed(() => (Array.isArray(msgStore.siteMessages) ? msgStore.siteMessages : []));
const siteLoading = computed(() => Boolean(msgStore.siteMessagesLoading));
const isSuper = computed(() => Boolean(store.isSuper));
const perms = computed(() => (Array.isArray(store.permissions) ? store.permissions.map(String) : []));
const hasPerm = (p) => (isSuper.value ? true : perms.value.includes(String(p)));
const hasAnyPerm = (arr) => (isSuper.value ? true : (arr || []).some((p) => perms.value.includes(String(p))));

const canViewHistory = computed(() => hasPerm('sys:notify:history'));
const canViewConfig = computed(() => hasPerm('sys:notify:config:view'));
const canEditConfig = computed(() => hasPerm('sys:notify:config:edit'));
const canTest = computed(() => hasPerm('sys:notify:test'));
const canSendSiteMessages = computed(() => isSuper.value);
const canSubscribeAlerts = computed(() => {
    return hasPerm('sys:alert:subscribe');
});
const testEmailTarget = ref('');
const isDev = Boolean(import.meta?.env?.DEV);
const wsStatus = computed(() => String(store.alertsWsStatus || 'disconnected'));

const alertsLevel = ref('all');
const alertsKeyword = ref('');
const alertsPaused = ref(false);
const alertsViewMode = ref('table');

const notificationsLevel = ref('all');
const notificationsKeyword = ref('');

const siteMessagesKeyword = ref('');
const siteMessagesUnreadOnly = computed({
    get: () => Boolean(msgStore.siteMessagesUnreadOnly),
    set: (v) => {
        msgStore.siteMessagesUnreadOnly = Boolean(v);
    },
});

const normalizeText = (v) => String(v ?? '').trim().toLowerCase();

const formatDateTime = (value) => {
    if (!value) return '';
    const d = new Date(value);
    if (Number.isNaN(d.getTime())) return String(value);
    return d.toLocaleString();
};

const matchesKeyword = (row, keyword, keys) => {
    const kw = normalizeText(keyword);
    if (!kw) return true;
    for (const k of keys) {
        if (normalizeText(row?.[k]).includes(kw)) return true;
    }
    return false;
};

const buildSiteMessageSnippet = (content) => {
    const raw = String(content ?? '').replace(/\s+/g, ' ').trim();
    if (!raw) return '';
    return raw.length > 60 ? `${raw.slice(0, 60)}...` : raw;
};

const filteredAlerts = computed(() => {
    const level = normalizeText(alertsLevel.value);
    return (alerts.value || [])
        .filter((a) => (level === 'all' ? true : normalizeText(a?.level) === level))
        .filter((a) => matchesKeyword(a, alertsKeyword.value, ['source', 'type', 'description']))
        .slice(0, 200)
        .map((a, idx) => ({ ...a, __rowKey: a?.id ?? `${a?.time ?? ''}-${idx}` }));
});

const timelineAlerts = computed(() => (filteredAlerts.value || []).slice(0, 50));

const alertStats = computed(() => {
    const list = alerts.value || [];
    const stats = { total: list.length, error: 0, warning: 0, success: 0, info: 0 };
    for (const a of list) {
        const lv = normalizeText(a?.level);
        if (lv && Object.prototype.hasOwnProperty.call(stats, lv)) stats[lv] += 1;
    }
    return stats;
});

const wsStatusText = computed(() => {
    if (wsStatus.value === 'connected') return '已连接';
    if (wsStatus.value === 'connecting') return '连接中';
    if (wsStatus.value === 'forbidden') return '无权限';
    if (wsStatus.value === 'error') return '异常';
    return '未连接';
});

const wsStatusEmoji = computed(() => {
    if (wsStatus.value === 'connected') return '🟢';
    if (wsStatus.value === 'connecting') return '🟡';
    if (wsStatus.value === 'forbidden') return '🟠';
    if (wsStatus.value === 'error') return '🔴';
    return '⚫';
});

const filteredNotifications = computed(() => {
    const level = normalizeText(notificationsLevel.value);
    return (notifications.value || [])
        .filter((n) => (level === 'all' ? true : normalizeText(n?.level) === level))
        .filter((n) => matchesKeyword(n, notificationsKeyword.value, ['device_name', 'message']))
        .slice(0, 200);
});

const filteredSiteMessages = computed(() => {
    return (siteMessages.value || [])
        .filter((m) => (siteMessagesUnreadOnly.value ? !m?.is_read : true))
        .filter((m) => matchesKeyword(m, siteMessagesKeyword.value, ['title', 'content', 'source', 'sender_name']))
        .slice(0, 1000);
});

const notificationStats = computed(() => {
    const list = notifications.value || [];
    const stats = { total: list.length, error: 0, warning: 0, info: 0 };
    for (const n of list) {
        const lv = normalizeText(n?.level);
        if (lv && Object.prototype.hasOwnProperty.call(stats, lv)) stats[lv] += 1;
    }
    return stats;
});

const siteMessageStats = computed(() => {
    const list = siteMessages.value || [];
    let unread = 0;
    let read = 0;
    for (const m of list) {
        if (m?.is_read) read += 1;
        else unread += 1;
    }
    return { total: list.length, unread, read };
});

const getAlertLevelType = (level) => {
    switch(level) {
        case 'error': return 'danger';
        case 'warning': return 'warning';
        case 'success': return 'success';
        default: return 'info';
    }
};

const clearAlerts = () => {
    alerts.value = [];
};
const lastHandledAlertSeq = ref(0);

const config = reactive({
    enable_email: false,
    email_config: {
        host: '',
        port: '',
        username: '',
        password: ''
    },
    enable_pushplus: false,
    pushplus_token: '',
    enable_http: false,
    http_url: ''
});

const getLevelType = (level) => {
    switch(level) {
        case 'error': return 'danger';
        case 'warning': return 'warning';
        case 'info': return 'info';
        default: return '';
    }
};

const buildTestNotifications = () => {
    const now = Date.now();
    const levels = ['info', 'warning', 'error'];
    return Array.from({ length: 12 }).map((_, idx) => {
        const createdAt = new Date(now - idx * 6 * 60 * 1000).toISOString();
        const level = levels[idx % levels.length];
        const deviceName = `DemoDevice-${String((idx % 5) + 1).padStart(2, '0')}`;
        const messageMap = {
            info: '配置已同步，设备状态正常',
            warning: '接口丢包升高，请关注链路质量',
            error: '设备离线，无法拉取监控数据',
        };
        return {
            id: `demo-notify-${idx}`,
            created_at: createdAt,
            level,
            device_name: deviceName,
            message: `${messageMap[level]}（测试消息 #${idx + 1}）`,
        };
    });
};

const buildTestSiteMessages = () => {
    const now = Date.now();
    const levels = ['info', 'warning', 'success'];
    const sources = ['系统', '管理员'];
    return Array.from({ length: 10 }).map((_, idx) => {
        const createdAt = new Date(now - idx * 10 * 60 * 1000).toISOString();
        const level = levels[idx % levels.length];
        const source = sources[idx % sources.length];
        return {
            id: `demo-site-${idx}`,
            created_at: createdAt,
            level,
            source,
            title: `站内消息标题 #${idx + 1}`,
            content: `这是一条站内消息（测试 #${idx + 1}）`,
            is_read: idx % 3 === 0,
            read_at: idx % 3 === 0 ? createdAt : null,
        };
    });
};

const buildTestAlerts = () => {
    const now = Date.now();
    const levels = ['warning', 'error', 'info', 'success'];
    const sources = ['SNMP', 'SSH', 'Sys', 'Collector'];
    const types = ['threshold', 'heartbeat', 'auth', 'latency'];
    return Array.from({ length: 18 }).map((_, idx) => {
        const time = new Date(now - idx * 2 * 60 * 1000).toISOString();
        const level = levels[idx % levels.length];
        return {
            id: `demo-alert-${idx}`,
            time,
            level,
            source: sources[idx % sources.length],
            type: types[idx % types.length],
            description: `模拟告警：${sources[idx % sources.length]} 检测到 ${types[idx % types.length]} 异常（测试 #${idx + 1}）`,
        };
    });
};

const fetchNotifications = async () => {
    loading.value = true;
    try {
        const res = await axios.get('/api/v1/notifications/history');
        if (res.data.code === 200) {
            notifications.value = res.data.data;
        }
    } catch (error) {
        ElMessage.error('获取通知失败');
    } finally {
        if (isDev && (!Array.isArray(notifications.value) || notifications.value.length === 0)) {
            notifications.value = buildTestNotifications();
        }
        loading.value = false;
    }
};

const loadSiteMessages = async () => {
    await msgStore.fetchLatestSiteMessages();
    await msgStore.fetchSiteMessageUnreadCount();
};

const markSiteMessageRead = async (row) => {
    const id = row?.id;
    if (!id) return;
    try {
        const res = await axios.post(`/api/v1/notifications/site-messages/${encodeURIComponent(id)}/read`);
        if (res?.data?.code === 200) {
            msgStore.applySiteMessageReadState(id, true);
            msgStore.fetchSiteMessageUnreadCount();
        } else {
            ElMessage.error(res?.data?.message || '操作失败');
        }
    } catch (e) {
        ElMessage.error('操作失败');
    }
};

const markSiteMessageUnread = async (row) => {
    const id = row?.id;
    if (!id) return;
    try {
        const res = await axios.post(`/api/v1/notifications/site-messages/${encodeURIComponent(id)}/unread`);
        if (res?.data?.code === 200) {
            msgStore.applySiteMessageReadState(id, false);
            msgStore.fetchSiteMessageUnreadCount();
        } else {
            ElMessage.error(res?.data?.message || '操作失败');
        }
    } catch (e) {
        ElMessage.error('操作失败');
    }
};

const goPublishPage = () => {
    router.push({ name: 'site-message-publish' });
};

const openSiteMessageDetail = (row) => {
    const id = row?.id;
    if (!id) return;
    router.push({ name: 'site-message-detail', params: { id: String(id) } });
};

const fetchConfig = async () => {
    configLoading.value = true;
    try {
        const res = await axios.get('/api/v1/notifications/config');
        if (res.data.code === 200) {
            const data = res.data.data;
            
            // 确保 email_config 结构完整，防止 v-model 报错
            if (!data.email_config) {
                data.email_config = {};
            }
            // 合并默认值
            data.email_config = {
                host: '',
                port: '',
                username: '',
                password: '',
                ...data.email_config
            };

            Object.assign(config, data);
        }
    } catch (error) {
        ElMessage.error('获取配置失败');
    } finally {
        configLoading.value = false;
    }
};

const saveConfig = async () => {
    try {
        const res = await axios.post('/api/v1/notifications/config', config);
        if (res.data.code === 200) {
            ElMessage.success('配置保存成功');
        } else {
            ElMessage.error(res.data.message || '保存失败');
        }
    } catch (error) {
        ElMessage.error('保存失败: ' + (error.response?.data?.detail?.message || error.message));
    }
};

const handleTest = async (channel) => {
    try {
        const payload = {
            channel: channel,
            config: config,
            target: channel === 'email' ? testEmailTarget.value : null
        };
        
        const res = await axios.post('/api/v1/notifications/test', payload);
        if (res.data.code === 200) {
            ElMessage.success('测试消息发送成功');
        } else {
            ElMessage.error(res.data.message || '测试失败');
        }
    } catch (error) {
        ElMessage.error('测试请求失败: ' + (error.response?.data?.detail?.message || error.message));
    }
};

onMounted(async () => {
    store.syncAuthFromToken();
    await store.fetchPermissions();
    const tab = String(route.query?.tab || '').trim();
    if (['site', 'notifications', 'settings'].includes(tab)) {
        activeTab.value = tab;
    }
    if (canViewHistory.value) fetchNotifications();
    if (!Array.isArray(msgStore.siteMessages) || msgStore.siteMessages.length === 0) loadSiteMessages();
    if (canViewConfig.value) fetchConfig();
});

watch(
    () => route.query?.tab,
    (tab) => {
        const t = String(tab || '').trim();
        if (['site', 'notifications', 'settings'].includes(t)) {
            activeTab.value = t;
        }
    }
);

watch(
    () => store.alertLastSeq,
    () => {
        const seq = Number(store.alertLastSeq || 0);
        if (!Number.isFinite(seq) || seq <= 0) return;
        if (seq <= Number(lastHandledAlertSeq.value || 0)) return;
        lastHandledAlertSeq.value = seq;
        if (alertsPaused.value) return;
        const alert = store.alertLastReceived;
        if (!alert || typeof alert !== 'object') return;
        alerts.value.unshift(alert);
        if (alerts.value.length > 500) alerts.value.pop();
    }
);

const tabSwitcherRef = ref(null);
const indicatorLeft = ref(0);
const indicatorWidth = ref(0);
const tabEls = reactive({});
let tabResizeObserver;

const visibleTabs = computed(() => {
    const tabs = [{ name: 'site', label: '站内消息', icon: Bell }];
    if (canViewHistory.value) tabs.push({ name: 'notifications', label: '设备通知（历史）', icon: Message });
    if (canViewConfig.value) tabs.push({ name: 'settings', label: '推送设置', icon: Setting });
    return tabs;
});

const indicatorStyle = computed(() => {
    return {
        width: `${indicatorWidth.value}px`,
        transform: `translate3d(${indicatorLeft.value}px, 0, 0)`,
    };
});

const setTabRef = (name, el) => {
    if (!name) return;
    if (el) tabEls[name] = el;
    else delete tabEls[name];
};

const updateIndicator = async () => {
    await nextTick();
    const el = tabEls[activeTab.value];
    const container = tabSwitcherRef.value;
    if (!el || !container) return;
    const c = container.getBoundingClientRect();
    const r = el.getBoundingClientRect();
    indicatorLeft.value = Math.max(0, r.left - c.left);
    indicatorWidth.value = Math.max(0, r.width);
};

watch(
    () => perms.value.join('|') + `:${isSuper.value}`,
    async () => {
        await nextTick();
        const names = visibleTabs.value.map(t => t.name);
        if (!names.includes(activeTab.value)) activeTab.value = names[0];
        await updateIndicator();
    },
    { immediate: true }
);

watch(
    () => activeTab.value,
    async () => {
        if (activeTab.value === 'site') loadSiteMessages();
        await updateIndicator();
    }
);

onMounted(async () => {
    await nextTick();
    await updateIndicator();
    if (tabSwitcherRef.value && typeof ResizeObserver !== 'undefined') {
        tabResizeObserver = new ResizeObserver(() => {
            updateIndicator();
        });
        tabResizeObserver.observe(tabSwitcherRef.value);
    }
});

onUnmounted(() => {
    if (tabResizeObserver) {
        tabResizeObserver.disconnect();
        tabResizeObserver = null;
    }
});
</script>

<style scoped>
.mc-container {
    --bg-dark: #f5f7fa;
    --bg-card: #ffffff;
    --bg-hover: #f0f2f5;
    --primary-color: #409eff;
    --text-primary: #303133;
    --text-secondary: #909399;
    --border-color: #dcdfe6;

    height: 100%;
    display: flex;
    flex-direction: column;
    background-color: var(--bg-dark);
    color: var(--text-primary);
    border-radius: 8px;
    overflow: hidden;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.mc-header {
    height: 60px;
    background-color: var(--bg-card);
    border-bottom: 1px solid var(--border-color);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 20px;
    flex-shrink: 0;
}

.page-title {
    font-size: 18px;
    font-weight: 600;
    display: flex;
    align-items: center;
    color: var(--text-primary);
}

.mr-2 {
    margin-right: 8px;
}

.info-icon {
    margin-left: 8px;
    color: var(--text-secondary);
    cursor: help;
    font-size: 16px;
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

.mc-content {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
}

.mc-topbar {
    padding: 14px 16px 0 16px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-shrink: 0;
}

.tab-switcher {
    position: relative;
    display: flex;
    width: 420px;
    max-width: 100%;
    background-color: var(--bg-hover);
    border-radius: 20px;
    padding: 4px;
}

.tab-item {
    flex: 1;
    padding: 6px 16px;
    cursor: pointer;
    border-radius: 16px;
    font-size: 14px;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 6px;
    color: var(--text-secondary);
    transition: all 0.22s;
    z-index: 1;
    user-select: none;
    white-space: nowrap;
}

.tab-item.active {
    color: #fff;
    font-weight: 500;
}

.tab-indicator {
    position: absolute;
    top: 4px;
    bottom: 4px;
    left: 0;
    background-color: var(--primary-color);
    border-radius: 16px;
    transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), width 0.22s cubic-bezier(0.22, 1, 0.36, 1);
    will-change: transform, width;
    z-index: 0;
    box-shadow: 0 2px 4px rgba(64, 158, 255, 0.3);
}

.topbar-right {
    display: flex;
    align-items: center;
    gap: 10px;
}

.status-pill {
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 999px;
    font-size: 12px;
    background: #ffffff;
    border: 1px solid #ebeef5;
}

.status-emoji {
    font-size: 14px;
    line-height: 14px;
}

.status-text {
    color: var(--text-secondary);
    line-height: 14px;
}

.mc-body {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    min-height: 0;
    padding: 12px 16px 16px 16px;
}

.tab-body {
    background: transparent;
    flex: 1;
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.stats-row {
    margin-bottom: 12px;
}
.stat-card {
    border: 1px solid #ebeef5;
    background: #ffffff;
    border-radius: 10px;
}
.stat-value {
    font-size: 22px;
    font-weight: 700;
    line-height: 28px;
}
.stat-value--danger {
    color: #f56c6c;
}
.stat-value--warning {
    color: #e6a23c;
}
.stat-label {
    margin-top: 6px;
    font-size: 12px;
    color: #909399;
}
.toolbar {
    padding: 10px 12px;
    background: #f7f8fa;
    border: 1px solid #ebeef5;
    border-radius: 6px;
    margin-bottom: 12px;
}
.toolbar__row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 12px;
    flex-wrap: wrap;
}
.toolbar__right {
    flex-shrink: 0;
}

.site-list {
    height: 100%;
    overflow: auto;
    border: 1px solid #ebeef5;
    border-radius: 10px;
    background: #ffffff;
}
.site-list__inner {
    padding: 12px;
    display: flex;
    flex-direction: column;
    gap: 10px;
    min-height: 100%;
}
.site-empty {
    padding: 30px 0;
}
.site-card {
    border: 1px solid #ebeef5;
    border-radius: 10px;
    cursor: pointer;
}
.site-card:hover {
    border-color: #c6e2ff;
}
.site-card--unread {
    background: #fff7e6;
    border-color: #ffe7ba;
}
.site-card--read {
    background: #ffffff;
}
.site-card__header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: 10px;
}
.site-card__title {
    font-weight: 600;
    line-height: 20px;
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.site-card__tags {
    display: flex;
    gap: 6px;
    flex-shrink: 0;
}
.site-card__content {
    margin-top: 8px;
    font-size: 13px;
    line-height: 18px;
    word-break: break-word;
    color: #606266;
}
.site-card__meta {
    margin-top: 10px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
}
.site-list__footer {
    padding: 8px 0 0;
    text-align: center;
}
.table {
    border: 1px solid #ebeef5;
    border-radius: 6px;
}

.table--fill {
    height: 100%;
}

.tab-main {
    flex: 1;
    min-height: 0;
}

.timeline-wrap {
    height: 100%;
    margin-bottom: 0;
}

.list-card {
    border: 1px solid #ebeef5;
    border-radius: 10px;
}

.list-card--fill {
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.list-card--fill :deep(.el-card__body) {
    flex: 1;
    min-height: 0;
    overflow: auto;
}
.timeline-item {
    display: flex;
    align-items: flex-start;
    gap: 10px;
}
.timeline-content {
    flex: 1;
    min-width: 0;
}
.timeline-title {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
}
.timeline-desc {
    margin-top: 4px;
    color: var(--text-primary);
    font-size: 13px;
    line-height: 18px;
    word-break: break-word;
}
.muted {
    color: var(--text-secondary);
}
.dot {
    color: var(--text-secondary);
}
.settings-card {
    border: 1px solid #ebeef5;
    border-radius: 8px;
    margin-bottom: 12px;
}
.settings-card__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
}
.settings-card__title {
    font-weight: 600;
}
.mb-12 {
    margin-bottom: 12px;
}
</style>
