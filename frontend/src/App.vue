<template>
    <div class="app">
        <router-view></router-view>
    </div>
</template>

<script setup>
import { h, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'
import { messageCenterDataStore } from '@/components/MessageCenter/date'
import { useDeviceStore } from '@/components/DeviceList/store'

const router = useRouter()
const store = homeDataStore()
const msgStore = messageCenterDataStore()
const deviceStore = useDeviceStore()

let authGuardTimer = null
let authRefreshListener = null
let authForceLoginListener = null
let notifyInitialized = false
const lastNotifiedSiteMessageId = ref('')
const currentUserId = ref(null)

const isAuthedArea = () => {
  const p = String(router.currentRoute?.value?.path || '')
  return p.startsWith('/user')
}

const setCurrentUserIdFromSession = (session) => {
  const id = Number(session?.id)
  currentUserId.value = Number.isFinite(id) ? id : null
}

const buildSnippet = (content) => {
  const raw = String(content ?? '').replace(/\s+/g, ' ').trim()
  if (!raw) return ''
  return raw.length > 60 ? `${raw.slice(0, 60)}...` : raw
}

const truncateText = (value, maxLen) => {
  const raw = String(value ?? '').replace(/\s+/g, ' ').trim()
  const n = Number(maxLen || 0)
  if (!raw) return ''
  if (!Number.isFinite(n) || n <= 0) return raw
  return raw.length > n ? `${raw.slice(0, n)}...` : raw
}

const notifySiteMessage = (msg) => {
  const id = msg?.id
  if (!id) return
  if (String(lastNotifiedSiteMessageId.value || '') === String(id)) return
  const senderId = Number(msg?.sender_id)
  if (Number.isFinite(senderId) && currentUserId.value !== null && senderId === currentUserId.value) return
  const current = router.currentRoute?.value
  if (current?.name === 'site-message-detail' && String(current?.params?.id || '') === String(id)) return

  const titleText = truncateText(msg?.title || '站内消息', 28)
  const contentText = truncateText(msg?.content, 80)

  const notif = ElNotification({
    title: '站内消息',
    message: h(
      'div',
      { style: { display: 'flex', flexDirection: 'column', gap: '6px' } },
      [
        h('div', { style: { fontWeight: '600', lineHeight: '18px' } }, titleText),
        h('div', { style: { lineHeight: '18px' } }, contentText),
        h('div', { style: { fontSize: '12px', color: '#909399', lineHeight: '16px' } }, '点击查看详情'),
      ]
    ),
    type: 'info',
    duration: 8000,
    onClick: () => {
      try {
        notif.close()
      } catch {}
      router.push({ name: 'site-message-detail', params: { id: String(id) } })
    },
  })

  lastNotifiedSiteMessageId.value = String(id)
  try {
    sessionStorage.setItem('siteMessage:lastNotifiedId', String(id))
  } catch {}
}

const normalizeLevel = (level) => String(level || '').trim().toLowerCase()

const notifyAlert = (alert) => {
  const level = normalizeLevel(alert?.level)
  const type = level === 'error' ? 'error' : level === 'warning' ? 'warning' : 'info'

  const deviceName = String(alert?.device_name || '').trim()
  const ipv4 = String(alert?.ipv4 || '').trim()
  const source = String(alert?.source || '系统').trim()
  const titleCore = deviceName ? deviceName : source
  const title = level ? `${level.toUpperCase()} - ${titleCore}` : titleCore

  const message = String(alert?.description || alert?.message || '').trim() || (ipv4 ? `IP: ${ipv4}` : '')
  if (!message) return

  const notif = ElNotification({
    title,
    message: buildSnippet(message),
    type,
    duration: level === 'error' ? 12000 : 9000,
    onClick: () => {
      try {
        notif.close()
      } catch {}
      router.push({ name: 'message', query: { tab: 'alerts' } })
    },
  })
}

const startRealtime = async () => {
  if (!isAuthedArea()) return
  const session = await store.ensureSession()
  if (!session) return
  setCurrentUserIdFromSession(session)
  store.syncAuthFromToken()
  await store.fetchPermissions()
  await msgStore.startSiteMessageRealtime()
  if (!notifyInitialized) {
    await msgStore.fetchLatestSiteMessages()
    const latestId = msgStore.siteMessages?.[0]?.id
    if (latestId) {
      lastNotifiedSiteMessageId.value = String(latestId)
      try {
        sessionStorage.setItem('siteMessage:lastNotifiedId', String(latestId))
      } catch {}
    } else {
      try {
        const cached = sessionStorage.getItem('siteMessage:lastNotifiedId')
        if (cached) lastNotifiedSiteMessageId.value = String(cached)
      } catch {}
    }
    notifyInitialized = true
  }
  await store.startAlertsRealtime()
}

const stopRealtime = () => {
  msgStore.stopSiteMessageRealtime()
  store.stopAlertsRealtime()
  deviceStore.stopRealtime()
  notifyInitialized = false
}

const stopAuthGuard = () => {
  if (!authGuardTimer) return
  clearInterval(authGuardTimer)
  authGuardTimer = null
}

const startAuthGuard = () => {
  stopAuthGuard()
  authGuardTimer = setInterval(async () => {
    if (!isAuthedArea()) return
    const session = await store.ensureSession()
    if (!session) {
      stopRealtime()
      return
    }
    setCurrentUserIdFromSession(session)
    await startRealtime()
  }, 30000)
}

onMounted(() => {
  authRefreshListener = async () => {
    if (!isAuthedArea()) return
    await startRealtime()
  }
  window.addEventListener('auth:refreshed', authRefreshListener)

  authForceLoginListener = () => {
    stopAuthGuard()
    stopRealtime()
    currentUserId.value = null
  }
  window.addEventListener('auth:force-login', authForceLoginListener)
})

watch(
  () => String(router.currentRoute?.value?.path || ''),
  async (path) => {
    if (String(path).startsWith('/user')) {
      await startRealtime()
      startAuthGuard()
      return
    }
    stopAuthGuard()
    stopRealtime()
    currentUserId.value = null
  },
  { immediate: true }
)

onBeforeUnmount(() => {
  stopAuthGuard()
  if (authRefreshListener) {
    window.removeEventListener('auth:refreshed', authRefreshListener)
    authRefreshListener = null
  }
  if (authForceLoginListener) {
    window.removeEventListener('auth:force-login', authForceLoginListener)
    authForceLoginListener = null
  }
  stopRealtime()
})

watch(
  () => msgStore.siteMessageLastSeq,
  () => {
    const msg = msgStore.siteMessageLastCreated
    if (msg) notifySiteMessage(msg)
  }
)

watch(
  () => msgStore.siteMessageUnreadCount,
  async (newCount, oldCount) => {
    if (!notifyInitialized) return
    const n = Number(newCount || 0)
    const o = Number(oldCount || 0)
    if (!Number.isFinite(n) || !Number.isFinite(o)) return
    if (n <= o) return
    await msgStore.fetchLatestSiteMessages()
    const list = Array.isArray(msgStore.siteMessages) ? msgStore.siteMessages : []
    const isSelfSent = (m) => {
      const senderId = Number(m?.sender_id)
      if (!Number.isFinite(senderId) || currentUserId.value === null) return false
      return senderId === currentUserId.value
    }
    const first =
      list.find((m) => m && typeof m === 'object' && !m.is_read && !isSelfSent(m)) ||
      list.find((m) => m && typeof m === 'object' && !isSelfSent(m)) ||
      null
    if (first) notifySiteMessage(first)
  }
)

watch(
  () => store.alertLastSeq,
  () => {
    const alert = store.alertLastReceived
    if (alert) notifyAlert(alert)
  }
)
</script>

<style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}

.app {
    width: 100vw;
    height: 100vh;
    /* background: linear-gradient(135deg, var(--dark), var(--primary)); */
    overflow: hidden;
}

/* 隐藏全局滚动条 */
html, body {
    overflow: hidden;
    scrollbar-width: none;
    -ms-overflow-style: none;
}

html::-webkit-scrollbar,
body::-webkit-scrollbar {
    display: none;
    width: 0;
}

/* 为所有非根元素启用滚动条 */
div::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

div::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 4px;
}

div::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
    border: none;
}

div::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
}

div {
    scrollbar-width: thin;
    scrollbar-color: #cbd5e1 #f1f5f9;
}
</style>
