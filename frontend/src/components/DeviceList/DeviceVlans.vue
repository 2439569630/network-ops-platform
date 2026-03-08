<template>
  <div class="device-vlans">
    <el-card shadow="never" class="vlan-card">
      <template #header>
        <div class="card-header">
          <span class="title">VLAN 信息</span>
          <div>
            <el-button type="success" size="small" :loading="syncing" @click="handleSync" style="margin-right: 8px">从设备同步</el-button>
            <el-button type="primary" size="small" :loading="loading" @click="refreshVlans">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="vlans" style="width: 100%">
        <el-table-column prop="vlan_id" label="VLAN ID" width="100" sortable />
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" />
        <!-- <el-table-column prop="ports" label="包含端口" min-width="200">
          <template #default="{ row }">
            <el-tag 
              v-for="port in row.ports" 
              :key="port" 
              size="small" 
              class="port-tag"
              effect="plain"
            >
              {{ port }}
            </el-tag>
          </template>
        </el-table-column> -->
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
const vlans = ref([])
let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let manualClose = false

const applyVlans = (rawList) => {
  const list = Array.isArray(rawList) ? rawList : []
  vlans.value = list.map(item => ({
    vlan_id: item.vlan_id || 0,
    name: item.name || `VLAN${item.vlan_id}`,
    status: (item.status || 'active').toLowerCase(),
    description: item.description || item.type || '',
    ports: Array.isArray(item.ports) ? item.ports : []
  }))
}

const fetchVlans = async ({ showLoading = false } = {}) => {
  if (!props.deviceId) return
  if (showLoading) loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/vlans/${props.deviceId}`)
    let rawList = []
    if (res?.data?.data && Array.isArray(res.data.data)) {
        rawList = res.data.data
    } else if (Array.isArray(res?.data)) {
        rawList = res.data
    } else if (Array.isArray(res)) {
        rawList = res
    }
    

    applyVlans(rawList)
  } catch (error) {
    ElMessage.error('获取VLAN列表失败')
    vlans.value = []
  } finally {
    if (showLoading) loading.value = false
  }
}

const refreshVlans = async () => {
  await fetchVlans({ showLoading: true })
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
      if (Array.isArray(data.vlans)) applyVlans(data.vlans)
      return
    }
    if (msg.type === 'resources_updated') {
      const res = Array.isArray(msg.resources) ? msg.resources : []
      if (res.includes('vlans')) {
        const data = msg.data || {}
        if (Array.isArray(data.vlans)) {
          applyVlans(data.vlans)
        } else {
          await fetchVlans({ showLoading: false })
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
  fetchVlans({ showLoading: false })
})

onBeforeUnmount(() => {
  closeWs()
})

watch(
  () => props.deviceId,
  () => {
    closeWs()
    fetchVlans({ showLoading: false })
    openWs()
  }
)
</script>

<style scoped>
.device-vlans {
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
.port-tag {
  margin-right: 4px;
  margin-bottom: 4px;
}
</style>
