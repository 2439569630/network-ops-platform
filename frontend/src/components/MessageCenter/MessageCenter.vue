<template>
  <div class="mc-container">
    <div class="mc-header">
      <div class="page-title">
        <el-icon class="mr-2"><Bell /></el-icon>
        <span>消息中心</span>
        <el-tooltip content="告警、通知与推送设置" placement="right">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="header-actions">
        <el-button size="small" @click="refreshAll">刷新</el-button>
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
          <div class="status-pill" :class="`status-pill--${wsStatus}`">
            <span class="status-emoji">{{ wsStatusEmoji }}</span>
            <span class="status-text">{{ wsStatusText }}</span>
          </div>
        </div>
      </div>

      <div class="mc-body">
        <div v-show="activeTab === 'alerts'" class="tab-body">
          <el-row :gutter="12" class="stats-row">
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ alertStats.total }}</div>
                <div class="stat-label">告警总数（本页缓存）</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value stat-value--danger">{{ alertStats.error }}</div>
                <div class="stat-label">错误</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value stat-value--warning">{{ alertStats.warning }}</div>
                <div class="stat-label">告警</div>
              </el-card>
            </el-col>
          </el-row>

          <el-alert
            v-if="wsStatus === 'forbidden'"
            type="warning"
            show-icon
            title="无权限订阅实时告警"
            class="mb-12"
          />

          <div class="toolbar">
            <el-space wrap alignment="center">
              <el-select v-model="alertsLevel" size="small" style="width: 140px">
                <el-option label="全部级别" value="all" />
                <el-option label="error" value="error" />
                <el-option label="warning" value="warning" />
                <el-option label="success" value="success" />
                <el-option label="info" value="info" />
              </el-select>
              <el-input v-model="alertsKeyword" size="small" clearable placeholder="搜索来源/类型/描述" style="width: 260px" />
              <el-radio-group v-model="alertsViewMode" size="small">
                <el-radio-button label="timeline">时间轴</el-radio-button>
                <el-radio-button label="table">表格</el-radio-button>
              </el-radio-group>
              <el-switch v-model="alertsPaused" inline-prompt active-text="暂停" inactive-text="实时" />
              <el-button size="small" @click="clearAlerts">清空</el-button>
            </el-space>
          </div>

          <div class="tab-main">
            <div v-if="alertsViewMode === 'timeline'" class="timeline-wrap">
              <el-card shadow="never" class="list-card list-card--fill">
                <el-timeline>
                  <el-timeline-item
                    v-for="a in timelineAlerts"
                    :key="a.__rowKey"
                    :timestamp="formatDateTime(a.time)"
                    :type="getAlertLevelType(a.level)"
                  >
                    <div class="timeline-item">
                      <el-tag :type="getAlertLevelType(a.level)" effect="light" size="small">
                        {{ String(a.level || '').toLowerCase() }}
                      </el-tag>
                      <div class="timeline-content">
                        <div class="timeline-title">
                          <span class="muted">{{ a.source }}</span>
                          <span class="dot">·</span>
                          <span class="muted">{{ a.type }}</span>
                        </div>
                        <div class="timeline-desc">{{ a.description }}</div>
                      </div>
                    </div>
                  </el-timeline-item>
                </el-timeline>
                <el-empty v-if="timelineAlerts.length === 0" description="暂无告警" />
              </el-card>
            </div>

            <el-table
              v-else
              :data="filteredAlerts"
              row-key="__rowKey"
              stripe
              height="100%"
              class="table table--fill"
              :empty-text="wsStatus === 'connected' ? '暂无实时告警' : '未连接或无数据'"
            >
              <el-table-column prop="time" label="时间" width="180">
                <template #default="scope">
                  {{ formatDateTime(scope.row.time) }}
                </template>
              </el-table-column>
              <el-table-column prop="level" label="级别" width="110">
                <template #default="scope">
                  <el-tag :type="getAlertLevelType(scope.row.level)" effect="light">{{ String(scope.row.level || '').toLowerCase() }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="source" label="来源" width="160" />
              <el-table-column prop="type" label="类型" width="160" />
              <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
            </el-table>
          </div>
        </div>

        <div v-show="activeTab === 'site'" class="tab-body">
          <el-row :gutter="12" class="stats-row">
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ siteMessageStats.total }}</div>
                <div class="stat-label">站内消息总数（最近200条）</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value stat-value--warning">{{ siteMessageStats.unread }}</div>
                <div class="stat-label">未读</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="stat-card">
                <div class="stat-value">{{ siteMessageStats.read }}</div>
                <div class="stat-label">已读</div>
              </el-card>
            </el-col>
          </el-row>

          <div class="toolbar">
            <el-space wrap alignment="center">
              <el-select v-model="siteMessagesLevel" size="small" style="width: 140px">
                <el-option label="全部级别" value="all" />
                <el-option label="warning" value="warning" />
                <el-option label="success" value="success" />
                <el-option label="info" value="info" />
              </el-select>
              <el-input v-model="siteMessagesKeyword" size="small" clearable placeholder="搜索标题/内容/来源" style="width: 260px" />
              <el-switch v-model="siteMessagesUnreadOnly" inline-prompt active-text="未读" inactive-text="全部" @change="fetchSiteMessages" />
              <el-button size="small" :loading="siteLoading" @click="fetchSiteMessages">刷新</el-button>
              <el-button v-if="canSendSiteMessages" size="small" type="primary" @click="openPublishDialog">发布</el-button>
            </el-space>
          </div>

          <div class="tab-main">
            <el-table
              :data="filteredSiteMessages"
              stripe
              v-loading="siteLoading"
              height="100%"
              class="table table--fill"
              empty-text="暂无站内消息"
            >
              <el-table-column prop="created_at" label="时间" width="180">
                <template #default="scope">
                  {{ formatDateTime(scope.row.created_at) }}
                </template>
              </el-table-column>
              <el-table-column prop="level" label="级别" width="110">
                <template #default="scope">
                  <el-tag :type="getSiteMessageLevelType(scope.row.level)" effect="light">{{ String(scope.row.level || '').toLowerCase() }}</el-tag>
                </template>
              </el-table-column>
              <el-table-column label="状态" width="110">
                <template #default="scope">
                  <el-tag :type="scope.row.is_read ? 'info' : 'warning'" effect="plain">
                    {{ scope.row.is_read ? '已读' : '未读' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="source" label="来源" width="160" show-overflow-tooltip />
              <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
              <el-table-column prop="content" label="内容" min-width="260" show-overflow-tooltip />
              <el-table-column label="操作" width="140" fixed="right">
                <template #default="scope">
                  <el-button
                    v-if="!scope.row.is_read"
                    size="small"
                    type="primary"
                    link
                    @click="markSiteMessageRead(scope.row)"
                  >
                    标记已读
                  </el-button>
                  <el-button
                    v-else
                    size="small"
                    link
                    @click="markSiteMessageUnread(scope.row)"
                  >
                    标记未读
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <el-dialog v-model="publishDialogVisible" title="发布站内消息" width="560px">
            <el-form label-position="top">
              <el-form-item label="标题">
                <el-input v-model="publishForm.title" maxlength="120" show-word-limit />
              </el-form-item>
              <el-form-item label="级别">
                <el-select v-model="publishForm.level" style="width: 180px">
                  <el-option label="info" value="info" />
                  <el-option label="success" value="success" />
                  <el-option label="warning" value="warning" />
                </el-select>
              </el-form-item>
              <el-form-item label="范围">
                <el-space wrap alignment="center">
                  <el-switch v-model="publishForm.is_global" inline-prompt active-text="全站" inactive-text="指定用户" />
                  <el-input
                    v-if="!publishForm.is_global"
                    v-model="publishForm.target_user_id"
                    placeholder="用户ID"
                    style="width: 180px"
                  />
                </el-space>
              </el-form-item>
              <el-form-item label="内容">
                <el-input v-model="publishForm.content" type="textarea" :rows="6" maxlength="2000" show-word-limit />
              </el-form-item>
            </el-form>
            <template #footer>
              <el-space>
                <el-button @click="publishDialogVisible = false">取消</el-button>
                <el-button type="primary" :loading="publishSubmitting" @click="submitPublish">发布</el-button>
              </el-space>
            </template>
          </el-dialog>
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
                    <el-form-item label="使用全局配置" v-if="canUseGlobal">
                      <el-switch v-model="config.use_global_email" :disabled="!canEditConfig" />
                    </el-form-item>

                    <el-row v-if="!config.use_global_email" :gutter="12">
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
import Cookies from 'js-cookie';
import { homeDataStore } from '@/components/home/home/data';
import { Bell, InfoFilled, WarningFilled, Message, Setting } from '@element-plus/icons-vue';

const activeTab = ref('site');
const notifications = ref([]);
const alerts = ref([]); // 实时告警列表
const siteMessages = ref([]);
const loading = ref(false);
const siteLoading = ref(false);
const configLoading = ref(false);
const store = homeDataStore();
const isSuper = computed(() => Boolean(store.isSuper));
const perms = computed(() => (Array.isArray(store.permissions) ? store.permissions.map(String) : []));
const hasPerm = (p) => (isSuper.value ? true : perms.value.includes(String(p)));
const hasAnyPerm = (arr) => (isSuper.value ? true : (arr || []).some((p) => perms.value.includes(String(p))));

const canViewHistory = computed(() => hasPerm('sys:notify:history'));
const canViewConfig = computed(() => hasPerm('sys:notify:config:view'));
const canEditConfig = computed(() => hasPerm('sys:notify:config:edit'));
const canTest = computed(() => hasPerm('sys:notify:test'));
const canSendSiteMessages = computed(() => hasPerm('sys:notify:global'));
const canUseGlobal = computed(() => {
    return hasPerm('sys:notify:global');
});
const canSubscribeAlerts = computed(() => {
    return hasPerm('sys:alert:subscribe');
});
const testEmailTarget = ref('');
const isDev = Boolean(import.meta?.env?.DEV);
let ws = null; // WebSocket 实例
let wsReconnectAttempted = false;
let wsReconnectTimer = null;
const wsStatus = ref('disconnected');
let siteAutoRefreshTimer = null;

const alertsLevel = ref('all');
const alertsKeyword = ref('');
const alertsPaused = ref(false);
const alertsViewMode = ref('table');

const notificationsLevel = ref('all');
const notificationsKeyword = ref('');

const siteMessagesLevel = ref('all');
const siteMessagesKeyword = ref('');
const siteMessagesUnreadOnly = ref(false);
const publishDialogVisible = ref(false);
const publishSubmitting = ref(false);
const publishForm = reactive({
    title: '',
    content: '',
    level: 'info',
    is_global: true,
    target_user_id: '',
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
    const level = normalizeText(siteMessagesLevel.value);
    return (siteMessages.value || [])
        .filter((m) => (level === 'all' ? true : normalizeText(m?.level) === level))
        .filter((m) => matchesKeyword(m, siteMessagesKeyword.value, ['title', 'content', 'source', 'sender_name']))
        .slice(0, 200);
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

const getSiteMessageLevelType = (level) => {
    const v = normalizeText(level);
    if (v === 'warning') return 'warning';
    if (v === 'success') return 'success';
    return 'info';
};

const clearAlerts = () => {
    alerts.value = [];
};

const initAlertWebSocket = () => {
    if (ws) {
        ws.__manualClose = true;
        ws.close();
        ws = null;
    }

    if (!canSubscribeAlerts.value) {
        wsStatus.value = 'forbidden';
        return;
    }

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.hostname
    const wsPort = window.location.port ? `:${window.location.port}` : ''
    const token = Cookies.get('token')
    const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/notifications/ws/alerts?token=${encodeURIComponent(token)}`
    
    try {
        wsStatus.value = 'connecting';
        ws = new WebSocket(wsUrl);
        ws.__manualClose = false;
        ws.onopen = () => {
            wsStatus.value = 'connected';
            wsReconnectAttempted = false;
        };
        ws.onmessage = (event) => {
            try {
                if (alertsPaused.value) return;
                const alert = JSON.parse(event.data);
                alerts.value.unshift(alert);
                if (alerts.value.length > 500) {
                    alerts.value.pop();
                }
            } catch (e) {
                wsStatus.value = 'error';
            }
        };
        ws.onclose = async (e) => {
            if (ws?.__manualClose) return;

            const closeCode = Number(e?.code || 0);
            if (closeCode === 4003) {
                wsStatus.value = 'forbidden';
                ElMessage.warning('无权订阅实时告警');
                return;
            }
            if (closeCode !== 4001) return;
            if (wsReconnectAttempted) return;
            wsReconnectAttempted = true;

            if (wsReconnectTimer) clearTimeout(wsReconnectTimer);
            wsReconnectTimer = setTimeout(async () => {
                try {
                    const res = await axios.post('/api/v1/auth/refresh');
                    const nextToken = res?.data?.token;
                    if (nextToken) Cookies.set('token', nextToken, { sameSite: 'lax' });
                    initAlertWebSocket();
                } catch (err) {
                    return;
                }
            }, 500);
        };
        ws.onerror = () => {
            wsStatus.value = 'error';
        };
    } catch (e) {
        wsStatus.value = 'error';
    }
}

const config = reactive({
    enable_email: false,
    use_global_email: false,
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

const fetchSiteMessages = async () => {
    siteLoading.value = true;
    try {
        const res = await axios.get('/api/v1/notifications/site-messages', {
            params: {
                limit: 200,
                offset: 0,
                unread_only: siteMessagesUnreadOnly.value ? 1 : 0,
            },
        });
        if (res.data.code === 200) {
            siteMessages.value = res.data.data;
            store.fetchSiteMessageUnreadCount();
        }
    } catch (error) {
        ElMessage.error('获取站内消息失败');
    } finally {
        if (isDev && (!Array.isArray(siteMessages.value) || siteMessages.value.length === 0)) {
            siteMessages.value = buildTestSiteMessages();
        }
        siteLoading.value = false;
    }
};

const markSiteMessageRead = async (row) => {
    const id = row?.id;
    if (!id) return;
    try {
        const res = await axios.post(`/api/v1/notifications/site-messages/${encodeURIComponent(id)}/read`);
        if (res?.data?.code === 200) {
            row.is_read = true;
            row.read_at = new Date().toISOString();
            store.fetchSiteMessageUnreadCount();
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
            row.is_read = false;
            row.read_at = null;
            store.fetchSiteMessageUnreadCount();
        } else {
            ElMessage.error(res?.data?.message || '操作失败');
        }
    } catch (e) {
        ElMessage.error('操作失败');
    }
};

const openPublishDialog = () => {
    publishForm.title = '';
    publishForm.content = '';
    publishForm.level = 'info';
    publishForm.is_global = true;
    publishForm.target_user_id = '';
    publishDialogVisible.value = true;
};

const submitPublish = async () => {
    if (publishSubmitting.value) return;
    publishSubmitting.value = true;
    try {
        const payload = {
            title: publishForm.title,
            content: publishForm.content,
            level: publishForm.level,
            is_global: !!publishForm.is_global,
            target_user_id: publishForm.is_global ? null : (publishForm.target_user_id ? Number(publishForm.target_user_id) : null),
            source: '管理员',
        };
        const res = await axios.post('/api/v1/notifications/site-messages', payload);
        if (res?.data?.code === 200) {
            ElMessage.success('发布成功');
            publishDialogVisible.value = false;
            await fetchSiteMessages();
        } else {
            ElMessage.error(res?.data?.message || '发布失败');
        }
    } catch (e) {
        ElMessage.error('发布失败');
    } finally {
        publishSubmitting.value = false;
    }
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

const refreshAll = async () => {
    if (canViewHistory.value) fetchNotifications();
    fetchSiteMessages();
    if (canViewConfig.value) fetchConfig();
    initAlertWebSocket();
};

onMounted(async () => {
    store.syncAuthFromToken();
    await store.fetchPermissions();
    if (canViewHistory.value) fetchNotifications();
    fetchSiteMessages();
    if (canViewConfig.value) fetchConfig();
    initAlertWebSocket(); // 启动 WS
    if (isDev) {
        setTimeout(() => {
            if (!Array.isArray(alerts.value) || alerts.value.length === 0) {
                alerts.value = buildTestAlerts();
            }
        }, 250);
    }
});

onUnmounted(() => {
    if (ws) {
        ws.__manualClose = true;
        ws.close();
    }
    if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
    }
    if (siteAutoRefreshTimer) {
        clearInterval(siteAutoRefreshTimer);
        siteAutoRefreshTimer = null;
    }
});

const tabSwitcherRef = ref(null);
const indicatorLeft = ref(0);
const indicatorWidth = ref(0);
const tabEls = reactive({});
let tabResizeObserver;

const visibleTabs = computed(() => {
    const tabs = [{ name: 'site', label: '站内消息', icon: Bell }];
    if (canSubscribeAlerts.value) tabs.push({ name: 'alerts', label: '实时告警', icon: WarningFilled });
    if (canViewHistory.value) tabs.push({ name: 'notifications', label: '设备通知', icon: Message });
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
        if (activeTab.value === 'site') fetchSiteMessages();
        await updateIndicator();
    }
);

onMounted(async () => {
    await nextTick();
    await updateIndicator();
    siteAutoRefreshTimer = setInterval(() => {
        if (activeTab.value === 'site') fetchSiteMessages();
    }, 30000);
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
