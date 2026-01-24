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
            <div class="content-text">{{ message.content }}</div>
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
import { ArrowLeft, Check, RefreshLeft } from '@element-plus/icons-vue';

const route = useRoute();
const router = useRouter();
const store = messageCenterDataStore();

const messageId = computed(() => Number(route.params.id));
const loading = ref(false);
const marking = ref(false);
const message = ref(null);

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

const fetchDetail = async () => {
  const cached = store.getSiteMessageById(messageId.value);
  if (cached) {
    message.value = cached;
    loading.value = false;
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
