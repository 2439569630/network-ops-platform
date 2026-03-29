import { defineStore } from 'pinia';
import { ref } from 'vue';
import axios from '@/axios/axios';

export const messageCenterDataStore = defineStore('messageCenterData', () => {
  let siteMessagePollTimer = null;
  let siteMessageEventSource = null;
  let siteMessageErrorRefreshAt = 0;

  const siteMessageUnreadCount = ref(0);
  const siteMessages = ref([]);
  const siteMessagesOffset = ref(0);
  const siteMessagesHasMore = ref(true);
  const siteMessagesLoading = ref(false);
  const siteMessagesLoadingMore = ref(false);
  const siteMessagesUnreadOnly = ref(false);
  const siteMessageLastSeq = ref(0);
  const siteMessageLastCreated = ref(null);

  const fetchSiteMessageUnreadCount = async () => {
    try {
      const res = await axios.get('/api/v1/notifications/site-messages/unread-count');
      if (res?.data?.code === 200) {
        const cnt = Number(res?.data?.data?.count || 0);
        siteMessageUnreadCount.value = Number.isFinite(cnt) ? cnt : 0;
      }
    } catch (e) {
      return;
    }
  };

  const hasSession = () => {
    try {
      return Boolean(sessionStorage.getItem('auth:session_cache:v1'));
    } catch {
      return false;
    }
  };

  const stopSiteMessageRealtime = () => {
    if (siteMessageEventSource) {
      try {
        siteMessageEventSource.close();
      } catch {}
      siteMessageEventSource = null;
    }
    if (siteMessagePollTimer) {
      clearInterval(siteMessagePollTimer);
      siteMessagePollTimer = null;
    }
  };

  const getSiteMessageById = (messageId) => {
    const id = Number(messageId);
    if (!Number.isFinite(id)) return null;
    const list = Array.isArray(siteMessages.value) ? siteMessages.value : [];
    return list.find((m) => Number(m?.id) === id) || null;
  };

  const upsertSiteMessage = (msg) => {
    if (!msg || typeof msg !== 'object') return;
    const id = Number(msg.id);
    if (!Number.isFinite(id)) return;
    const list = Array.isArray(siteMessages.value) ? siteMessages.value : [];
    const idx = list.findIndex((m) => Number(m?.id) === id);
    if (idx >= 0) {
      Object.assign(list[idx], msg);
      siteMessages.value = list.slice(0, 20);
      return;
    }
    siteMessages.value = [msg, ...list].slice(0, 20);
  };

  const applySiteMessageReadState = (messageId, isRead) => {
    const id = Number(messageId);
    if (!Number.isFinite(id)) return;
    const list = Array.isArray(siteMessages.value) ? siteMessages.value : [];
    const idx = list.findIndex((m) => Number(m?.id) === id);
    if (idx < 0) return;
    list[idx].is_read = Boolean(isRead);
    list[idx].read_at = Boolean(isRead) ? (list[idx].read_at || new Date().toISOString()) : null;
    siteMessages.value = list;
  };

  const removeSiteMessage = (messageId) => {
    const id = Number(messageId);
    if (!Number.isFinite(id)) return;
    const list = Array.isArray(siteMessages.value) ? siteMessages.value : [];
    siteMessages.value = list.filter((m) => Number(m?.id) !== id);
  };

  const fetchLatestSiteMessages = async () => {
    try {
      const res = await axios.get('/api/v1/notifications/site-messages', {
        params: {
          unread_only: siteMessagesUnreadOnly.value ? 1 : 0,
        },
      });
      if (res?.data?.code !== 200) return;
      const items = Array.isArray(res?.data?.data) ? res.data.data : [];
      siteMessages.value = items.slice(0, 20);
    } catch (e) {
      return;
    }
  };

  const resetAndLoadSiteMessages = async (options = {}) => {
    const unreadOnly = Boolean(options.unreadOnly);
    siteMessagesUnreadOnly.value = unreadOnly;
    siteMessagesOffset.value = 0;
    siteMessagesHasMore.value = true;
    siteMessages.value = [];
    await loadMoreSiteMessages();
  };

  const loadMoreSiteMessages = async () => {
    if (siteMessagesLoading.value || siteMessagesLoadingMore.value) return;
    if (!siteMessagesHasMore.value) return;
    const isFirst = Number(siteMessagesOffset.value || 0) === 0;
    if (isFirst) siteMessagesLoading.value = true;
    else siteMessagesLoadingMore.value = true;
    try {
      const limit = 20;
      const offset = Number(siteMessagesOffset.value || 0);
      const res = await axios.get('/api/v1/notifications/site-messages', {
        params: {
          limit,
          offset,
          unread_only: siteMessagesUnreadOnly.value ? 1 : 0,
        },
      });
      if (res?.data?.code === 200) {
        const items = Array.isArray(res?.data?.data) ? res.data.data : [];
        siteMessages.value = (Array.isArray(siteMessages.value) ? siteMessages.value : []).concat(items);
        siteMessagesOffset.value = offset + items.length;
        siteMessagesHasMore.value = items.length === limit;
      }
    } catch (e) {
      return;
    } finally {
      siteMessagesLoading.value = false;
      siteMessagesLoadingMore.value = false;
    }
  };

  const startSiteMessageRealtime = async () => {
    if (siteMessageEventSource || siteMessagePollTimer) return;
    await fetchSiteMessageUnreadCount();

    const url = '/api/v1/notifications/sse/site-messages';
    try {
      if (typeof EventSource === 'undefined') throw new Error('EventSource unavailable');
      try {
        siteMessageEventSource = new EventSource(url, { withCredentials: true });
      } catch {
        siteMessageEventSource = new EventSource(url);
      }

      siteMessageEventSource.addEventListener('unread', (evt) => {
        try {
          const data = JSON.parse(String(evt?.data || '{}'));
          const cnt = Number(data?.count || 0);
          siteMessageUnreadCount.value = Number.isFinite(cnt) ? cnt : 0;
        } catch {
          return;
        }
      });

      siteMessageEventSource.addEventListener('message', (evt) => {
        try {
          const data = JSON.parse(String(evt?.data || '{}'));
          const msg = data?.message && typeof data.message === 'object' ? data.message : null;
          if (!msg) return;
          if (msg.is_read === undefined) msg.is_read = false;
          if (msg.read_at === undefined) msg.read_at = null;
          upsertSiteMessage(msg);
          siteMessageLastCreated.value = msg;
          siteMessageLastSeq.value += 1;
        } catch {
          return;
        }
      });

      siteMessageEventSource.addEventListener('read_state', (evt) => {
        try {
          const data = JSON.parse(String(evt?.data || '{}'));
          const messageId = Number(data?.message_id);
          const isRead = Boolean(data?.is_read);
          applySiteMessageReadState(messageId, isRead);
        } catch {
          return;
        }
      });

      siteMessageEventSource.addEventListener('deleted', (evt) => {
        try {
          const data = JSON.parse(String(evt?.data || '{}'));
          const messageId = Number(data?.message_id);
          removeSiteMessage(messageId);
        } catch {
          return;
        }
      });

      siteMessageEventSource.onerror = async () => {
        if (!hasSession()) {
          stopSiteMessageRealtime();
          return;
        }
        const ts = Date.now();
        if (ts - siteMessageErrorRefreshAt < 10000) return;
        siteMessageErrorRefreshAt = ts;
        await fetchSiteMessageUnreadCount();
        await fetchLatestSiteMessages();
      };
    } catch (e) {
      if (!hasSession()) return;
      await fetchLatestSiteMessages();
      siteMessagePollTimer = setInterval(async () => {
        await fetchSiteMessageUnreadCount();
        await fetchLatestSiteMessages();
      }, 30000);
    }
  };

  const resetForLogout = () => {
    stopSiteMessageRealtime();
    siteMessageErrorRefreshAt = 0;
    siteMessageUnreadCount.value = 0;
    siteMessages.value = [];
    siteMessagesOffset.value = 0;
    siteMessagesHasMore.value = true;
    siteMessagesLoading.value = false;
    siteMessagesLoadingMore.value = false;
    siteMessagesUnreadOnly.value = false;
    siteMessageLastSeq.value = 0;
    siteMessageLastCreated.value = null;
  };

  return {
    siteMessageUnreadCount,
    siteMessages,
    siteMessagesOffset,
    siteMessagesHasMore,
    siteMessagesLoading,
    siteMessagesLoadingMore,
    siteMessagesUnreadOnly,
    siteMessageLastSeq,
    siteMessageLastCreated,
    fetchSiteMessageUnreadCount,
    fetchLatestSiteMessages,
    resetAndLoadSiteMessages,
    loadMoreSiteMessages,
    getSiteMessageById,
    upsertSiteMessage,
    applySiteMessageReadState,
    removeSiteMessage,
    startSiteMessageRealtime,
    stopSiteMessageRealtime,
    resetForLogout,
  };
});
