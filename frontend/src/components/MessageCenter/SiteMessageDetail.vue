<template>
  <div class="smd-container">
    <div class="smd-topbar">
      <div class="topbar-left" @click="goBack">
        <el-icon class="back-icon"><ArrowLeft /></el-icon>
        <span>返回列表</span>
      </div>
    </div>

    <div class="smd-scroll-area">
      <div class="smd-paper" v-loading="loading">
        <template v-if="message">
          <div class="smd-paper__header">
            <div class="smd-title-row">
              <h1 class="smd-title">{{ message.title }}</h1>
              <div class="smd-actions">
                <el-tooltip content="标记为已读" v-if="!message.is_read">
                  <el-button circle size="small" type="success" plain @click="markRead">
                    <el-icon><Check /></el-icon>
                  </el-button>
                </el-tooltip>
                <el-tooltip content="标记为未读" v-if="message.is_read">
                  <el-button circle size="small" type="info" plain @click="markUnread">
                    <el-icon><RefreshLeft /></el-icon>
                  </el-button>
                </el-tooltip>
              </div>
            </div>

            <div class="smd-meta-row">
              <div class="meta-info">
                <el-avatar
                  :size="28"
                  :src="message.sender_avatar_url || undefined"
                  :icon="message.sender_avatar_url ? undefined : avatarConfig.icon"
                  class="meta-avatar"
                  :style="message.sender_avatar_url ? {} : { backgroundColor: avatarConfig.bg, color: avatarConfig.color }"
                />
                <span class="sender-name">{{ message.sender_name || message.source || '系统消息' }}</span>
                <span class="meta-dot">·</span>
                <span class="send-time">{{ formatDateTime(message.created_at) }}</span>
              </div>
              <el-tag :type="message.is_read ? 'info' : 'danger'" size="small" effect="plain" round>
                {{ message.is_read ? '已读' : '未读' }}
              </el-tag>
            </div>
          </div>

          <el-divider class="smd-divider" />

          <div class="smd-paper__content">
            <div class="content-text">{{ formatCenterMessage(message.content) }}</div>
          </div>
        </template>

        <div v-else-if="!loading" class="smd-empty">
          <el-empty description="消息不存在或无权限查看" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import { messageCenterDataStore } from '@/components/MessageCenter/date';
import { ArrowLeft, BellFilled, Check, RefreshLeft, UserFilled } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const store = messageCenterDataStore();

const messageId = computed(() => Number(route.params.id));
const loading = ref(false);
const marking = ref(false);
const message = ref(null);

const normalizeText = (value) => String(value ?? '').trim().toLowerCase();

const getAvatarConfig = (row) => {
  const source = normalizeText(row?.source);
  const sender = normalizeText(row?.sender_name);
  if (source.includes('系统') || source.includes('system') || (!sender && !source)) {
    return { icon: BellFilled, color: '#409eff', bg: '#ecf5ff' };
  }
  return { icon: UserFilled, color: '#909399', bg: '#f4f4f5' };
};

const avatarConfig = computed(() => getAvatarConfig(message.value));

const formatDateTime = (value) => {
  if (!value) return '';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return String(value);
  return d.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  });
};

const humanizeMetricKey = (key) => {
  const raw = String(key || '').trim();
  if (!raw) return '';

  const tokenUpperMap = {
    cpu: 'CPU',
    ip: 'IP',
    ssh: 'SSH',
    snmp: 'SNMP',
    mac: 'MAC',
    vlan: 'VLAN',
    qos: 'QoS',
    poe: 'PoE',
    rx: 'RX',
    tx: 'TX',
    oid: 'OID',
  };

  const [base, suffix] = raw.split(':', 2);
  const words = String(base || '')
    .split('_')
    .map((w) => String(w || '').trim())
    .filter(Boolean)
    .map((w) => tokenUpperMap[w.toLowerCase()] || (w[0] ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(' ');

  if (suffix) return `${words}（${suffix}）`;
  return words;
};

const formatMetric = (metric) => {
  const m = String(metric || '').trim();
  if (!m) return '';

  if (m.startsWith('if_phy_down:')) {
    const iface = m.split(':', 2)[1] || '';
    return iface ? `接口物理 Down（${iface}）` : '接口物理 Down';
  }
  if (m.startsWith('if_protocol_down:')) {
    const iface = m.split(':', 2)[1] || '';
    return iface ? `接口协议 Down（${iface}）` : '接口协议 Down';
  }

  const map = {
    cpu_usage: 'CPU 使用率',
    memory_usage: '内存使用率',
    disk_usage: '磁盘使用率',
    temperature: '温度',
    online_status: '在线状态',
    if_phy_down_count: '接口物理 Down 数',
    if_protocol_down_count: '接口协议 Down 数',
  };
  return map[m] || humanizeMetricKey(m) || m;
};

const formatOfflineReason = (reason) => {
  const raw = String(reason || '').trim();
  if (!raw) return '';
  const low = raw.toLowerCase();

  if (low.includes('timed out') || low.includes('timeout') || low.includes('read timeout') || low.includes('netmikotimeoutexception')) {
    return '连接超时';
  }
  if (
    low.includes('netmikoauthenticationexception') ||
    low.includes('authentication failed') ||
    low.includes('bad authentication type') ||
    low.includes('not allowed')
  ) {
    return '认证失败';
  }
  if (
    low.includes('connection refused') ||
    low.includes('no route to host') ||
    low.includes('name or service not known') ||
    low.includes('nodename nor servname') ||
    low.includes('unreachable')
  ) {
    return '不可达';
  }
  if (
    low.includes('connection reset by peer') ||
    low.includes('broken pipe') ||
    low.includes('socket is closed') ||
    low.includes('eoferror') ||
    low.includes('bad file descriptor')
  ) {
    return '连接中断';
  }

  const stripped = raw.replace(/^[A-Za-z_][A-Za-z0-9_]*?(Exception|Error):\s*/u, '').trim();
  return stripped || raw;
};

const formatCenterMessage = (messageText) => {
  const raw = String(messageText ?? '').trim();
  if (!raw) return '';

  if (raw.startsWith('触发告警:')) {
    return raw.replace(/^触发告警:\s*([^\s]+)\s*/u, (_m, metric) => `触发告警: ${formatMetric(metric)} `).trim();
  }
  if (raw.startsWith('告警恢复:')) {
    return raw.replace(/^告警恢复:\s*([^\s]+)\s*/u, (_m, metric) => `告警恢复: ${formatMetric(metric)} `).trim();
  }
  if (raw.startsWith('设备离线:')) {
    const reason = raw.slice('设备离线:'.length).trim();
    const label = formatOfflineReason(reason);
    return label ? `设备离线: ${label}` : '设备离线';
  }

  const low = raw.toLowerCase();
  if (low.includes('netmikotimeoutexception')) return '连接超时';
  if (low.includes('netmikoauthenticationexception')) return '认证失败';

  const stripped = raw.replace(/\b[A-Za-z_][A-Za-z0-9_]*?(Exception|Error):\s*/gu, '').trim();
  return stripped || raw;
};

const fetchDetail = async () => {
  const cached = store.getSiteMessageById(messageId.value);
  if (cached) {
    message.value = cached;
    loading.value = false;
    if (cached?.sender_id && !cached?.sender_avatar_url) {
      try {
        const res = await axios.get(`/api/v1/notifications/site-messages/${encodeURIComponent(messageId.value)}`);
        if (res?.data?.code === 200 && res?.data?.data) {
          store.upsertSiteMessage(res.data.data);
          message.value = store.getSiteMessageById(messageId.value) || message.value;
        }
      } catch (e) {}
    }
    if (message.value && !message.value.is_read) await markRead({ silent: true });
    await store.fetchSiteMessageUnreadCount();
    return;
  }
  loading.value = true;
  try {
    const res = await axios.get(`/api/v1/notifications/site-messages/${encodeURIComponent(messageId.value)}`);
    if (res?.data?.code === 200) {
      message.value = res?.data?.data || null;
      if (message.value) store.upsertSiteMessage(message.value);
      message.value = store.getSiteMessageById(messageId.value) || message.value;
      if (message.value && !message.value.is_read) await markRead({ silent: true });
      await store.fetchSiteMessageUnreadCount();
    } else {
      message.value = null;
    }
  } catch (e) {
    message.value = null;
  } finally {
    loading.value = false;
  }
};

const markRead = async (options = {}) => {
  if (!message.value?.id) return;
  if (marking.value) return;
  marking.value = true;
  try {
    const res = await axios.post(`/api/v1/notifications/site-messages/${encodeURIComponent(message.value.id)}/read`);
    if (res?.data?.code === 200) {
      store.applySiteMessageReadState(message.value.id, true);
      message.value = store.getSiteMessageById(message.value.id) || message.value;
      if (!options.silent) ElMessage.success('已标记已读');
      await store.fetchSiteMessageUnreadCount();
    } else if (!options.silent) {
      ElMessage.error(res?.data?.message || '操作失败');
    }
  } catch (e) {
    if (!options.silent) ElMessage.error('操作失败');
  } finally {
    marking.value = false;
  }
};

const markUnread = async () => {
  if (!message.value?.id) return;
  if (marking.value) return;
  marking.value = true;
  try {
    const res = await axios.post(`/api/v1/notifications/site-messages/${encodeURIComponent(message.value.id)}/unread`);
    if (res?.data?.code === 200) {
      store.applySiteMessageReadState(message.value.id, false);
      message.value = store.getSiteMessageById(message.value.id) || message.value;
      ElMessage.success('已标记未读');
      await store.fetchSiteMessageUnreadCount();
    } else {
      ElMessage.error(res?.data?.message || '操作失败');
    }
  } catch (e) {
    ElMessage.error('操作失败');
  } finally {
    marking.value = false;
  }
};

const goBack = () => {
  router.back();
};

watch(
  () => messageId.value,
  async (id) => {
    if (!id) return;
    await fetchDetail();
  },
  { immediate: true }
);
</script>

<style scoped>
.smd-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f5f7fa;
}

.smd-topbar {
  height: 50px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  padding: 0 20px;
}

.topbar-left {
  display: flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
  color: #606266;
  font-size: 14px;
  transition: color 0.2s;
}

.topbar-left:hover {
  color: #409eff;
}

.back-icon {
  font-size: 16px;
}

.smd-scroll-area {
  flex: 1;
  overflow-y: auto;
  padding: 0 20px 40px 20px;
  display: flex;
  justify-content: center;
}

.smd-paper {
  width: 100%;
  max-width: 900px;
  background: #ffffff;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
  padding: 40px;
  margin-top: 10px;
  min-height: 400px;
  display: flex;
  flex-direction: column;
}

.smd-paper__header {
  margin-bottom: 20px;
}

.smd-title-row {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}

.smd-title {
  margin: 0;
  font-size: 24px;
  font-weight: 700;
  color: #303133;
  line-height: 1.4;
  word-break: break-word;
}

.smd-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.meta-info {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #909399;
  font-size: 14px;
}

.meta-avatar {
  flex-shrink: 0;
}

.sender-name {
  font-weight: 600;
  color: #606266;
}

.meta-dot {
  font-weight: bold;
}

.smd-divider {
  margin: 0 0 30px 0;
}

.smd-paper__content {
  flex: 1;
  font-size: 16px;
  line-height: 1.8;
  color: #303133;
}

.content-text {
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
}

.smd-empty {
  margin-top: 100px;
}
</style>
