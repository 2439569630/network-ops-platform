<template>
  <div class="smd-container">
    <div class="smd-header">
      <el-button @click="goBack">返回</el-button>
      <div class="smd-title">{{ message?.title || '站内消息' }}</div>
      <div class="smd-actions">
        <el-button v-if="message && !message.is_read" type="primary" :loading="marking" @click="markRead">标记已读</el-button>
        <el-button v-if="message && message.is_read" :loading="marking" @click="markUnread">标记未读</el-button>
      </div>
    </div>

    <el-card v-loading="loading" shadow="never" class="smd-card">
      <div v-if="message" class="smd-meta">
        <div class="smd-meta__row">
          <el-tag :type="message.is_read ? 'info' : 'warning'" effect="plain">
            {{ message.is_read ? '已读' : '未读' }}
          </el-tag>
        </div>
        <div class="smd-meta__row">
          <div class="smd-meta__item"><span class="k">发件人</span><span class="v">{{ message.sender_name || message.source || '-' }}</span></div>
          <div class="smd-meta__item"><span class="k">时间</span><span class="v">{{ formatDateTime(message.created_at) }}</span></div>
        </div>
      </div>

      <el-empty v-if="!loading && !message" description="消息不存在或无权限查看" />

      <div v-if="message" class="smd-content">
        <pre class="smd-content__pre">{{ message.content }}</pre>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import { messageCenterDataStore } from '@/components/MessageCenter/date';

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
  return d.toLocaleString();
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
  gap: 12px;
}

.smd-header {
  display: flex;
  align-items: center;
  gap: 12px;
}

.smd-title {
  font-size: 18px;
  font-weight: 600;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.smd-actions {
  display: flex;
  gap: 8px;
}

.smd-card {
  flex: 1;
  overflow: hidden;
}

.smd-meta {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 12px;
}

.smd-meta__row {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}

.smd-meta__item {
  display: flex;
  gap: 8px;
  align-items: baseline;
}

.k {
  color: #909399;
}

.v {
  color: #303133;
}

.smd-content__pre {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: inherit;
  line-height: 1.7;
}
</style>
