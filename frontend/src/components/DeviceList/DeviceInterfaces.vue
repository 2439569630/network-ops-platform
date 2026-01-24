<template>
  <div class="device-interfaces">
    <el-card shadow="never" class="interface-card">
      <template #header>
        <div class="card-header">
          <span class="title">接口列表</span>
          <div>
            <el-button type="success" size="small" :loading="syncing" @click="handleSync" style="margin-right: 8px">从设备同步</el-button>
            <el-button type="warning" size="small" @click="openDetail">查看插槽0详情</el-button>
            <el-button type="primary" size="small" :loading="loading" @click="refreshInterfaces">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="interfaces" style="width: 100%">
        <el-table-column prop="name" label="接口名称" min-width="140" fixed />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'up' ? 'success' : 'danger'" effect="dark">
              {{ row.status.toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" min-width="140" />
        <el-table-column prop="mac_address" label="MAC地址" min-width="140" />
        <el-table-column prop="speed" label="速率" width="100" />
        <el-table-column prop="duplex" label="双工" width="100" />
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
      </el-table>
    </el-card>
    <el-drawer v-model="detailOpen" title="插槽0接口详情" size="60%" :with-header="true">
    <div class="drawer-toolbar">
      <el-input v-model="filterText" placeholder="按名称搜索" clearable style="max-width: 220px" />
      <el-select v-model="filterStatus" placeholder="状态" style="max-width: 160px">
        <el-option label="全部" value="all" />
        <el-option label="up" value="up" />
        <el-option label="down" value="down" />
      </el-select>
    </div>
    <el-table :data="filteredDetail" style="width: 100%">
      <el-table-column prop="name" label="接口名称" min-width="160" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
          <el-tag size="small" :type="statusOf(row) === 'up' ? 'success' : 'danger'" effect="dark">
            {{ statusOf(row).toUpperCase() }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="ip_address" label="IP地址" min-width="140" />
        <el-table-column prop="mac_address" label="MAC地址" min-width="140" />
        <el-table-column prop="speed" label="速率" width="100" />
        <el-table-column prop="duplex" label="双工" width="100" />
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
        <el-table-column prop="input_rate_bps" label="入速率(bps)" width="140" />
        <el-table-column prop="output_rate_bps" label="出速率(bps)" width="140" />
      <el-table-column type="expand">
        <template #default="{ row }">
          <el-descriptions title="总量统计" column="2" class="desc-block" border>
            <el-descriptions-item>
              <template #label><span class="text-zh">入包数</span><span class="text-en">(Input Packets)</span></template>
              <span class="text-zh">{{ humanNum(row.input_packets_total) }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">入字节</span><span class="text-en">(Input Bytes)</span></template>
              <span class="text-zh">{{ humanBytes(row.input_bytes_total) }}</span>
              <span class="text-en">({{ humanNum(row.input_bytes_total) }} B)</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">出包数</span><span class="text-en">(Output Packets)</span></template>
              <span class="text-zh">{{ humanNum(row.output_packets_total) }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">出字节</span><span class="text-en">(Output Bytes)</span></template>
              <span class="text-zh">{{ humanBytes(row.output_bytes_total) }}</span>
              <span class="text-en">({{ humanNum(row.output_bytes_total) }} B)</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="基础信息" column="3" class="desc-block" border>
            <el-descriptions-item>
              <template #label>
                <span class="text-zh">描述</span><span class="text-en">(Description)</span>
              </template>
              <span class="text-zh">{{ row.description || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label>
                <span class="text-zh">MTU</span><span class="text-en">(Maximum Transmit Unit)</span>
              </template>
              <span class="text-zh">{{ row.mtu ?? '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label>
                <span class="text-zh">端口模式</span><span class="text-en">(Port Mode)</span>
              </template>
              <span class="text-zh">{{ (row.port_mode || '').replace('COMMON', '普通').replace('FORCE', '强制').replace('COPPER', '铜缆') || '-' }}</span>
              <span class="text-en">({{ row.port_mode || '' }})</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label>
                <span class="text-zh">协商</span><span class="text-en">(Negotiation)</span>
              </template>
              <span class="text-zh">{{ row.negotiation === 'ENABLE' ? '开启' : (row.negotiation === 'DISABLE' ? '关闭' : (row.negotiation || '-')) }}</span>
              <span class="text-en">({{ row.negotiation || '' }})</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label>
                <span class="text-zh">MDI</span><span class="text-en">(MDI/MDIX)</span>
              </template>
              <span class="text-zh">{{ row.mdi || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label>
                <span class="text-zh">环回</span><span class="text-en">(Loopback)</span>
              </template>
              <span class="text-zh">{{ row.loopback || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="时间戳" column="3" class="desc-block" border>
            <el-descriptions-item>
              <template #label><span class="text-zh">协议上线</span><span class="text-en">(Line Up)</span></template>
              <span class="text-zh">{{ row.last_line_protocol_up || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">物理上线</span><span class="text-en">(Phy Up)</span></template>
              <span class="text-zh">{{ row.last_phy_up || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">物理下线</span><span class="text-en">(Phy Down)</span></template>
              <span class="text-zh">{{ row.last_phy_down || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">当前时间</span><span class="text-en">(Current)</span></template>
              <span class="text-zh">{{ row.current_time || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="速率与峰值" column="2" class="desc-block" border>
            <el-descriptions-item>
              <template #label><span class="text-zh">入速率</span><span class="text-en">(Input Rate)</span></template>
              <span class="text-zh">{{ humanBps(row.input_rate_bps) }} / {{ (row.input_rate_pps ?? 0) + ' pps' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">出速率</span><span class="text-en">(Output Rate)</span></template>
              <span class="text-zh">{{ humanBps(row.output_rate_bps) }} / {{ (row.output_rate_pps ?? 0) + ' pps' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">入峰值</span><span class="text-en">(Input Peak)</span></template>
              <span class="text-zh">{{ humanBps(row.input_peak_bps) }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">峰值记录</span><span class="text-en">(Peak Time)</span></template>
              <span class="text-zh">{{ row.input_peak_time || '-' }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">出峰值</span><span class="text-en">(Output Peak)</span></template>
              <span class="text-zh">{{ humanBps(row.output_peak_bps) }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">峰值记录</span><span class="text-en">(Peak Time)</span></template>
              <span class="text-zh">{{ row.output_peak_time || '-' }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-row :gutter="12" class="desc-block">
            <el-col :span="12">
              <el-card shadow="never">
                <div>输入利用率</div>
                <el-progress :percentage="fmtPct(row.input_utilization)" :status="fmtPct(row.input_utilization) > fmtPct(row.input_util_threshold) ? 'exception' : 'success'"></el-progress>
                <div>阈值：{{ fmtPct(row.input_util_threshold) }}%</div>
              </el-card>
            </el-col>
            <el-col :span="12">
              <el-card shadow="never">
                <div>输出利用率</div>
                <el-progress :percentage="fmtPct(row.output_utilization)" :status="fmtPct(row.output_utilization) > fmtPct(row.output_util_threshold) ? 'exception' : 'success'"></el-progress>
                <div>阈值：{{ fmtPct(row.output_util_threshold) }}%</div>
              </el-card>
            </el-col>
          </el-row>
          <el-descriptions title="输入计数" column="4" class="desc-block" border>
            <el-descriptions-item>
              <template #label><span class="text-zh">单播</span><span class="text-en">(Unicast)</span></template>
              <span class="text-zh">{{ row.input_unicast ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">多播</span><span class="text-en">(Multicast)</span></template>
              <span class="text-zh">{{ row.input_multicast ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">广播</span><span class="text-en">(Broadcast)</span></template>
              <span class="text-zh">{{ row.input_broadcast ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">巨帧</span><span class="text-en">(Jumbo)</span></template>
              <span class="text-zh">{{ row.input_jumbo ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">丢弃</span><span class="text-en">(Discard)</span></template>
              <span class="text-zh">{{ row.input_discard ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">错误</span><span class="text-en">(Error)</span></template>
              <span class="text-zh">{{ row.input_error ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">CRC</span><span class="text-en">(CRC)</span></template>
              <span class="text-zh">{{ row.input_crc ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">巨帧</span><span class="text-en">(Giants)</span></template>
              <span class="text-zh">{{ row.input_giants ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">乱喷</span><span class="text-en">(Jabbers)</span></template>
              <span class="text-zh">{{ row.input_jabbers ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">节流</span><span class="text-en">(Throttles)</span></template>
              <span class="text-zh">{{ row.input_throttles ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">小包</span><span class="text-en">(Runts)</span></template>
              <span class="text-zh">{{ row.input_runts ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">符号错误</span><span class="text-en">(Symbols)</span></template>
              <span class="text-zh">{{ row.input_symbols ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">忽略</span><span class="text-en">(Ignoreds)</span></template>
              <span class="text-zh">{{ row.input_ignoreds ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">帧数</span><span class="text-en">(Frames)</span></template>
              <span class="text-zh">{{ row.input_frames ?? 0 }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="输出计数" column="4" class="desc-block" border>
            <el-descriptions-item>
              <template #label><span class="text-zh">单播</span><span class="text-en">(Unicast)</span></template>
              <span class="text-zh">{{ row.output_unicast ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">多播</span><span class="text-en">(Multicast)</span></template>
              <span class="text-zh">{{ row.output_multicast ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">广播</span><span class="text-en">(Broadcast)</span></template>
              <span class="text-zh">{{ row.output_broadcast ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">巨帧</span><span class="text-en">(Jumbo)</span></template>
              <span class="text-zh">{{ row.output_jumbo ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">丢弃</span><span class="text-en">(Discard)</span></template>
              <span class="text-zh">{{ row.output_discard ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">错误</span><span class="text-en">(Error)</span></template>
              <span class="text-zh">{{ row.output_error ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">碰撞</span><span class="text-en">(Collisions)</span></template>
              <span class="text-zh">{{ row.output_collisions ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">过多碰撞</span><span class="text-en">(ExcessiveCollisions)</span></template>
              <span class="text-zh">{{ row.output_excessive_collisions ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">迟到碰撞</span><span class="text-en">(Late Collisions)</span></template>
              <span class="text-zh">{{ row.output_late_collisions ?? 0 }}</span>
            </el-descriptions-item>
            <el-descriptions-item>
              <template #label><span class="text-zh">延迟发送</span><span class="text-en">(Deferreds)</span></template>
              <span class="text-zh">{{ row.output_deferreds ?? 0 }}</span>
            </el-descriptions-item>
          </el-descriptions>
          <el-descriptions title="原始回显" :column="1" class="desc-block" border>
            <el-descriptions-item label="Raw">
              <el-input type="textarea" :rows="8" :readonly="true" :value="row.raw_block || ''" />
            </el-descriptions-item>
          </el-descriptions>
        </template>
      </el-table-column>
      </el-table>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, watch } from 'vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import Cookies from 'js-cookie'

const props = defineProps({
  deviceId: {
    type: [Number, String],
    default: null
  }
})

const loading = ref(false)
const syncing = ref(false)
const interfaces = ref([])
const detailOpen = ref(false)
const detailLoading = ref(false)
const detailList = ref([])
const filterText = ref('')
const filterStatus = ref('all')
let ws = null
let reconnectTimer = null
let reconnectAttempts = 0
let manualClose = false

const humanBps = (v) => {
  const n = Number(v || 0)
  if (n >= 1e9) return (n / 1e9).toFixed(2) + ' Gbps'
  if (n >= 1e6) return (n / 1e6).toFixed(2) + ' Mbps'
  if (n >= 1e3) return (n / 1e3).toFixed(2) + ' Kbps'
  return n + ' bps'
}
const fmtPct = (v) => {
  const n = Number(v || 0)
  if (!isFinite(n)) return 0
  return Math.max(0, Math.min(100, n))
}
const humanBytes = (v) => {
  const n = Number(v || 0)
  if (!isFinite(n) || n < 0) return '0 B'
  if (n >= 1 << 30) return (n / (1 << 30)).toFixed(2) + ' GB'
  if (n >= 1 << 20) return (n / (1 << 20)).toFixed(2) + ' MB'
  if (n >= 1 << 10) return (n / (1 << 10)).toFixed(2) + ' KB'
  return n + ' B'
}
const humanNum = (v) => {
  const n = Number(v || 0)
  if (!isFinite(n)) return '0'
  return n.toLocaleString()
}
const statusOf = (item) => {
  const s = (item?.protocol_state || item?.phy_state || 'down').toLowerCase()
  return s
}
const filteredDetail = computed(() => {
  const kw = String(filterText.value || '').trim().toLowerCase()
  const st = String(filterStatus.value || 'all')
  return (detailList.value || []).filter(it => {
    const name = String(it?.name || '').toLowerCase()
    const matchKw = !kw || name.includes(kw)
    const stv = statusOf(it)
    const matchSt = st === 'all' || st === stv
    return matchKw && matchSt
  })
})

const applyInterfaces = (rawList) => {
  const list = Array.isArray(rawList) ? rawList : []
  interfaces.value = list.map(item => ({
    name: item.name || '',
    status: (item.protocol_state || item.phy_state || 'down').toLowerCase(),
    ip_address: item.ip_address || '-', // 待后端完善解析
    mac_address: item.mac_address || '-',
    speed: item.speed || '-',
    duplex: item.duplex || '-',
    description: item.description || ''
  }))
}

const fetchInterfaces = async ({ showLoading = false } = {}) => {
  if (!props.deviceId) return
  if (showLoading) loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/interfaces/${props.deviceId}`)
    // 后端返回标准结构 { code: 200, data: [...] }，需要解包两层 data
    const rawList = Array.isArray(res?.data?.data) 
      ? res.data.data 
      : (Array.isArray(res?.data) ? res.data : [])
    applyInterfaces(rawList)
  } catch (error) {
    ElMessage.error('获取接口列表失败')
    interfaces.value = []
  } finally {
    if (showLoading) loading.value = false
  }
}

const refreshInterfaces = async () => {
  await fetchInterfaces({ showLoading: true })
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

const fetchDetail = async (slot = 0) => {
  if (!props.deviceId) return
  const slotId = Number(slot) || 0
  detailLoading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/interfaces/detail/${props.deviceId}`, { params: { slot: slotId } })
    const rawList = Array.isArray(res?.data?.data)
      ? res.data.data
      : (Array.isArray(res?.data) ? res.data : [])
    detailList.value = rawList
  } catch (error) {
    ElMessage.error('获取插槽0详情失败')
    detailList.value = []
  } finally {
    detailLoading.value = false
  }
}

const openDetail = async () => {
  if (!props.deviceId) return
  detailOpen.value = true
  await fetchDetail(0)
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
  const token = Cookies.get('token')
  if (!token) return

  manualClose = false
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = normalizeHostname(window.location.hostname)
  const wsPort = window.location.port ? `:${window.location.port}` : ''
  const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/user/device/ws/resources/${props.deviceId}?token=${encodeURIComponent(token)}`

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
      if (Array.isArray(data.interfaces)) {
        applyInterfaces(data.interfaces)
      }
      if (detailOpen.value && Array.isArray(data.interfaces_slot0_detailed)) {
        detailList.value = data.interfaces_slot0_detailed
      }
      return
    }
    if (msg.type === 'resources_updated') {
      const res = Array.isArray(msg.resources) ? msg.resources : []
      const data = msg.data || {}
      if (res.includes('interfaces')) {
        if (Array.isArray(data.interfaces)) {
          applyInterfaces(data.interfaces)
        } else {
          await fetchInterfaces({ showLoading: false })
        }
      }
      if (detailOpen.value && res.includes('interfaces_slot0_detailed')) {
        if (Array.isArray(data.interfaces_slot0_detailed)) {
          detailList.value = data.interfaces_slot0_detailed
        } else {
          await fetchDetail(0)
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
        const res = await axios.post('/api/v1/auth/refresh')
        const nextToken = res?.data?.token
        if (nextToken) {
          Cookies.set('token', nextToken, { sameSite: 'lax' })
          reconnectAttempts = 0
          openWs()
        }
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
  fetchInterfaces({ showLoading: false })
})

onBeforeUnmount(() => {
  closeWs()
})

watch(
  () => props.deviceId,
  () => {
    closeWs()
    fetchInterfaces({ showLoading: false })
    if (detailOpen.value) fetchDetail(0)
    openWs()
  }
)
</script>

<style scoped>
.device-interfaces {
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
.drawer-toolbar {
  display: flex;
  gap: 12px;
  margin-bottom: 12px;
}
.status-tag {
  margin-left: 8px;
}
.desc-block {
  margin-top: 8px;
}
.text-zh {
  font-size: 14px;
  color: var(--el-text-color-primary);
}
.text-en {
  font-size: 12px;
  color: #909399;
  margin-left: 4px;
}
</style>
