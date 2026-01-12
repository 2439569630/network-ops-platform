<template >
  <div class="common-layout">
    <el-container>
      <el-container class="container">
        <el-aside class="aside"> <LEFT /> </el-aside>
        <el-main class="main"> <RouterView></RouterView> </el-main>
      </el-container>
    </el-container>
  </div>
</template>
<script setup>
import heada from './header.vue';
import DATE from './home/home.vue'
import LEFT from './left/left.vue'
import { onBeforeUnmount, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElNotification } from 'element-plus'
import Cookies from 'js-cookie'
import { homeDataStore } from '@/components/home/home/data'

const router = useRouter()
const store = homeDataStore()

const buildSnippet = (content) => {
  const raw = String(content ?? '').replace(/\s+/g, ' ').trim()
  if (!raw) return ''
  return raw.length > 60 ? `${raw.slice(0, 60)}...` : raw
}

const notifySiteMessage = (msg) => {
  const id = msg?.id
  if (!id) return
  const current = router.currentRoute?.value
  if (current?.name === 'site-message-detail' && String(current?.params?.id || '') === String(id)) return

  const notif = ElNotification({
    title: String(msg?.title || '站内消息'),
    message: buildSnippet(msg?.content),
    type: 'info',
    duration: 8000,
    onClick: () => {
      try {
        notif.close()
      } catch {}
      router.push({ name: 'site-message-detail', params: { id: String(id) } })
    },
  })
}

watch(
  () => store.siteMessageLastSeq,
  () => {
    const msg = store.siteMessageLastCreated
    if (msg) notifySiteMessage(msg)
  }
)

onMounted(async () => {
  const token = Cookies.get('token')
  if (!token) return
  store.syncAuthFromToken()
  await store.fetchPermissions()
  await store.startSiteMessageRealtime()
})

onBeforeUnmount(() => {
  store.stopSiteMessageRealtime()
})


</script>
<style scoped>
.common-layout{
    width: 100vw;
    height: 100vh;
    color: #fff;
}

.aside {
    width: clamp(220px, 15vw, 300px);
    min-width: 220px;
    height: 100vh;
    border-right: none;
    /* background: rgba(45, 55, 72, 0.6); */
}
.main {
    width: auto;
    flex: 1;
    /* background: rgba(45, 55, 72, 0.6); */
    height: 100vh;
    padding: 0;
}

.common-layout :deep(.el-main) {
    padding: 0;
}

@media (max-width: 900px) {
    .aside {
        width: 64px;
        min-width: 64px;
    }

    .aside :deep(.el-menu-item span),
    .aside :deep(.el-sub-menu__title span) {
        display: none;
    }

    .aside :deep(.el-menu-item),
    .aside :deep(.el-sub-menu__title) {
        justify-content: center;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }
}
</style>
