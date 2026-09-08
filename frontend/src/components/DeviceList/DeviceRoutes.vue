<template>
  <div class="device-routes">
    <el-card shadow="never" class="route-card">
      <template #header>
        <div class="card-header">
          <span class="title">路由表</span>
          <div>
            <el-button type="success" size="small" :loading="syncing" @click="handleSync" style="margin-right: 8px">从设备同步</el-button>
            <el-button type="primary" size="small" :loading="loading" @click="refreshRoutes">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="routes" style="width: 100%">
        <el-table-column prop="destination" label="目的网络" min-width="140" />
        <el-table-column prop="mask" label="掩码" width="120" />
        <el-table-column prop="gateway" label="下一跳" min-width="140" />
        <el-table-column prop="interface" label="出接口" min-width="120" />
        <el-table-column prop="protocol" label="协议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="getProtocolType(row.protocol)">{{ row.protocol }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="metric" label="Metric" width="80" />
        <!-- <el-table-column prop="updated_at" label="更新时间" width="180" /> -->
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'

const props = defineProps({
  deviceId: {
    type: [Number, String],
    default: null
  }
})

const loading = ref(false)
const syncing = ref(false)
const routes = ref([])
let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let manualClose = false

const getProtocolType = (proto) => {
  const p = (proto || '').toLowerCase()
  if (p === 'direct') return 'success'
  if (p === 'static') return 'info'
  if (p.includes('ospf')) return 'warning'
  if (p.includes('bgp')) return 'danger'
  return ''
}

const applyRoutes = (rawList) => {
  const list = Array.isArray(rawList) ? rawList : []
  routes.value = list.map(item => ({
    destination: item.destination || item.network || '',
    mask: item.mask || item.netmask || '',
    gateway: item.nexthop || item.gateway || item.next_hop || '-',
    interface: item.interface || '-',
    protocol: item.protocol || item.proto || 'Unknown',
    metric: item.metric || item.cost || 0,
    updated_at: item.updated_at || '-'
  }))
}

const fetchRoutes = async ({ showLoading = false } = {}) => {
  if (!props.deviceId) return
  if (showLoading) loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/routes/${props.deviceId}`)
    // 后端返回 JSON 列表，字段映射需要根据 netmiko/huawei 解析结果调整
    
    let rawList = []
    if (res?.data?.data && Array.isArray(res.data.data)) {
        rawList = res.data.data
    } else if (Array.isArray(res?.data)) {
        rawList = res.data
    } else if (Array.isArray(res)) {
        rawList = res
    }
    
    applyRoutes(rawList)
  } catch (error) {
    ElMessage.error('获取路由表失败')
    routes.value = []
  } finally {
    if (showLoading) loading.value = false
  }
}

const refreshRoutes = async () => {
  await fetchRoutes({ showLoading: true })
}

const handleSync = async () => {
  if (!props.deviceId) return
  syncing.value = true
  try {
    await axios.post(`/api/v1/user/device/resources/sync/${props.deviceId}`)
    ElMessage.success('同步任务已触发，请稍后刷新')
  } catch (error) {
    ElMessage.error('触发同步失败')
  } finally {
    syncing.value = false
  }
}

const normalizeHostname = (hostname) => {
  const h = String(hostname || '').trim()
  if (!h || h === '0.0.0.0') return '127.0.0.1'
  return h
}

const closeWs = () => {
  manualClose = true
  if (reconnectTimer) {
    clearTimeout(reconnectTimer)
    reconnectTimer = null
  }
  try {
    if (ws) ws.close()
  } catch {}
  ws = null
}

const openWs = () => {
  if (!props.deviceId) return
  try {
    if (!sessionStorage.getItem('auth:session_cache:v1')) return
  } catch {}

  manualClose = false
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = normalizeHostname(window.location.hostname)
  const wsPort = window.location.port ? `:${window.location.port}` : ''
  const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/user/device/ws/resources/${props.deviceId}`

  try {
    ws = new WebSocket(wsUrl)
  } catch {
    ws = null
    return
  }

  ws.onopen = () => {
    reconnectAttempts = 0
  }

  ws.onmessage = async (evt) => {
    let msg = null
    try {
      msg = JSON.parse(evt.data)
    } catch {
      msg = null
    }
    if (!msg || typeof msg !== 'object') return
    if (msg.type === 'resources_snapshot') {
      const data = msg.data || {}
      if (Array.isArray(data.routes)) applyRoutes(data.routes)
      return
    }
    if (msg.type === 'resources_updated') {
      const res = Array.isArray(msg.resources) ? msg.resources : []
      if (res.includes('routes')) {
        const data = msg.data || {}
        if (Array.isArray(data.routes)) {
          applyRoutes(data.routes)
        } else {
          await fetchRoutes({ showLoading: false })
        }
      }
    }
  }

  ws.onclose = async (e) => {
    ws = null
    if (manualClose) return

    if (e?.code === 4003) return

    if (e?.code === 4001) {
      try {
        await axios.post('/api/v1/auth/refresh')
        reconnectAttempts = 0
        openWs()
      } catch {
        return
      }
      return
    }

    const delay = Math.min(30000, 1000 * Math.pow(2, reconnectAttempts))
    reconnectAttempts++
    reconnectTimer = setTimeout(() => {
      openWs()
    }, delay)
  }
}

onMounted(() => {
  openWs()
  fetchRoutes({ showLoading: false })
})

onBeforeUnmount(() => {
  closeWs()
})

watch(
  () => props.deviceId,
  () => {
    closeWs()
    fetchRoutes({ showLoading: false })
    openWs()
  }
)
</script>

<style scoped>
.device-routes {
  margin-top: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: 600;
}
</style>
