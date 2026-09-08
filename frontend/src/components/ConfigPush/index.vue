<template>
  <div class="page" :class="{ 'is-mobile': isMobile }">
    <el-card class="card">
      <template #header>
        <div class="header">
          <div class="header-left">
            <span class="title">配置下发</span>
            <div class="tags-group">
              <el-tag v-if="jobId" class="job-tag" effect="dark">{{ `任务 #${jobId}` }}</el-tag>
              <el-tag v-if="jobStatus" class="job-tag" :type="jobStatusType" effect="dark">{{ statusText(jobStatus) }}</el-tag>
            </div>
          </div>
          <div class="header-actions">
            <el-button type="primary" :disabled="running" @click="startJob" :size="isMobile ? 'small' : 'default'">{{ isMobile ? '开始' : '开始下发' }}</el-button>
            <el-button type="warning" :disabled="!jobId" @click="cancelJob" :size="isMobile ? 'small' : 'default'">{{ isMobile ? '取消' : '取消任务' }}</el-button>
            <el-button @click="resetAll" :size="isMobile ? 'small' : 'default'">清空</el-button>
          </div>
        </div>
      </template>

      <div class="form">
        <el-form :label-width="isMobile ? 'auto' : '90px'" :label-position="isMobile ? 'top' : 'right'">
          <el-form-item label="任务标题">
            <el-input v-model="title" placeholder="可选，默认：配置下发任务" />
          </el-form-item>
          <el-form-item label="选择设备">
            <el-select
              v-model="selectedDeviceIds"
              multiple
              filterable
              collapse-tags
              collapse-tags-tooltip
              placeholder="选择需要下发的设备"
              style="width: 100%"
            >
              <el-option
                v-for="d in devices"
                :key="d.id"
                :label="`${d.device_name} (${d.ipv4 || '-'})`"
                :value="d.id"
              />
            </el-select>
          </el-form-item>
          <el-form-item label="导入命令">
            <el-upload
              :auto-upload="false"
              :show-file-list="false"
              accept=".txt"
              :on-change="handleFileChange"
            >
              <el-button type="info" :size="isMobile ? 'small' : 'default'">选择 txt 文件</el-button>
            </el-upload>
          </el-form-item>
          <el-form-item label="命令列表">
            <el-input
              v-model="commandsText"
              type="textarea"
              :rows="isMobile ? 5 : 8"
              placeholder="每行一条命令；空行会被忽略；以 # 开头的行会被忽略"
            />
          </el-form-item>
        </el-form>
      </div>

      <div class="outputs" v-if="jobId">
        <el-tabs v-model="activeTab" type="border-card" class="device-tabs">
          <el-tab-pane
            v-for="d in selectedDevices"
            :key="d.id"
            :label="tabLabel(d.id)"
            :name="String(d.id)"
          >
            <div class="output-meta">
              <el-tag :type="deviceStatusType(deviceState[d.id]?.status)" effect="dark" size="small">
                {{ statusText(deviceState[d.id]?.status || 'pending') }}
              </el-tag>
              <span class="meta-text">{{ `${d.device_name}  ${d.ipv4 || ''}` }}</span>
            </div>
            <pre class="output-box">{{ deviceState[d.id]?.text || '' }}</pre>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import axios from '@/axios/axios'
import { ElNotification } from 'element-plus'

const isMobile = ref(window.innerWidth < 768)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }

const devices = ref([])
const selectedDeviceIds = ref([])
const title = ref('')
const commandsText = ref('')
const jobId = ref(null)
const jobStatus = ref('')
const lastId = ref('0-0')
const activeTab = ref('')
const running = ref(false)
const deviceState = reactive({})

let ws = null
let syncTimer = null

const selectedDevices = computed(() => {
  const ids = new Set(selectedDeviceIds.value.map(x => Number(x)))
  return (devices.value || []).filter(d => ids.has(Number(d.id)))
})

const statusTextMap = {
  pending: '待执行',
  running: '执行中',
  success: '成功',
  failed: '失败',
  partial: '部分成功',
  canceled: '已取消',
  canceling: '取消中',
  finished: '已结束',
}

const statusText = (status) => {
  const s = String(status || '').trim()
  return statusTextMap[s] || s
}

const jobStatusType = computed(() => {
  const s = String(jobStatus.value || '')
  if (s === 'success') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'partial') return 'warning'
  if (s === 'canceled') return 'info'
  if (s === 'canceling') return 'warning'
  if (s === 'running') return 'primary'
  return 'info'
})

const ensureDeviceState = (deviceId) => {
  const did = String(deviceId)
  if (!deviceState[did]) {
    deviceState[did] = { status: 'pending', text: '' }
  }
  return deviceState[did]
}

const tabLabel = (deviceId) => {
  const did = String(deviceId)
  const d = (devices.value || []).find(x => String(x.id) === did)
  const st = ensureDeviceState(did)
  const name = d ? String(d.device_name || did) : did
  return `${name} (${statusText(st.status || 'pending')})`
}

const deviceStatusType = (status) => {
  const s = String(status || '')
  if (s === 'success') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'canceled') return 'info'
  if (s === 'running') return 'primary'
  return 'warning'
}

const appendOutput = (deviceId, line) => {
  const st = ensureDeviceState(deviceId)
  st.text = `${st.text || ''}${String(line || '')}\n`
}

const isTerminalStatus = (status) => {
  const s = String(status || '').trim()
  return ['success', 'failed', 'partial', 'canceled', 'finished'].includes(s)
}

const stopSyncTimer = () => {
  if (syncTimer) {
    clearTimeout(syncTimer)
    syncTimer = null
  }
}

const scheduleJobSync = (delay = 1500) => {
  stopSyncTimer()
  if (!jobId.value) return
  if (isTerminalStatus(jobStatus.value)) return
  syncTimer = window.setTimeout(() => {
    syncJobState()
  }, delay)
}

const syncJobState = async () => {
  if (!jobId.value) return
  try {
    const res = await axios.get(`/api/v1/config-push/jobs/${jobId.value}`)
    const payload = res?.data?.data || {}
    const job = payload?.job || {}
    const items = Array.isArray(payload?.items) ? payload.items : []

    if (job?.status) {
      jobStatus.value = String(job.status)
      running.value = !isTerminalStatus(job.status)
    }

    for (const item of items) {
      const did = String(item?.device_id ?? '')
      if (!did) continue
      const st = ensureDeviceState(did)
      st.status = String(item?.status || st.status || 'pending')
      if (item?.error_message && !String(st.text || '').includes(String(item.error_message))) {
        appendOutput(did, `失败: ${String(item.error_message)}`)
      }
    }

    if (isTerminalStatus(job?.status)) {
      closeWs()
      stopSyncTimer()
      return
    }
  } catch (e) {}
  scheduleJobSync()
}

const handleEvent = (evt) => {
  if (!evt || typeof evt !== 'object') return
  if (evt.id) lastId.value = String(evt.id)
  const type = String(evt.type || '')
  const deviceId = evt.device_id != null ? String(evt.device_id) : null

  if (type === 'job_started') {
    jobStatus.value = 'running'
    running.value = true
    scheduleJobSync()
    return
  }
  if (type === 'job_finished') {
    jobStatus.value = String(evt.status || 'finished')
    running.value = false
    stopSyncTimer()
    closeWs()
    return
  }
  if (type === 'job_cancel_requested') {
    jobStatus.value = 'canceling'
    scheduleJobSync()
    return
  }
  if (deviceId) {
    const st = ensureDeviceState(deviceId)
    if (type === 'item_started') st.status = 'running'
    if (type === 'item_success') st.status = 'success'
    if (type === 'item_failed') {
      st.status = 'failed'
      const code = String(evt.error || '').trim()
      const holder = String(evt.lock_holder || '').trim()
      const ttl = String(evt.lock_ttl || '').trim()
      const msg =
        code === 'device_locked' ? '设备连接占用中（可能有其它下发/SSH 会话占用，或存在遗留锁）' :
        code === 'device_missing' ? '设备不存在或已删除' :
        (code || '执行失败')
      const extra = [holder ? `占用者=${holder}` : '', ttl ? `锁TTL=${ttl}` : ''].filter(Boolean).join(' ')
      appendOutput(deviceId, `失败: ${msg}${extra ? ` (${extra})` : ''}`)
    }
    if (type === 'item_canceled') st.status = 'canceled'
    if (type === 'device_error') {
      st.status = 'failed'
      appendOutput(deviceId, `设备错误: ${String(evt.error || '')}`)
    }
    if (type === 'command_error') {
      st.status = 'failed'
      appendOutput(deviceId, `命令错误: ${String(evt.command || '')}`)
      appendOutput(deviceId, String(evt.error || ''))
    }
    if (type === 'command_output') {
      const cmd = String(evt.command || '')
      if (cmd) appendOutput(deviceId, `> ${cmd}`)
      const content = String(evt.content || '')
      if (content) appendOutput(deviceId, content)
    }
  }
}

const openWs = () => {
  closeWs()
  if (!jobId.value) return
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsHost = window.location.hostname
  const wsPort = window.location.port ? `:${window.location.port}` : ''
  const url = `${wsProtocol}//${wsHost}${wsPort}/api/v1/config-push/ws/${jobId.value}?last_id=${encodeURIComponent(lastId.value)}`
  ws = new WebSocket(url)
  ws.onmessage = (event) => {
    let payload = null
    try {
      payload = JSON.parse(event.data)
    } catch (e) {
      payload = null
    }
    handleEvent(payload)
  }
  ws.onopen = () => {}
  ws.onclose = async (e) => {
    const closeCode = Number(e?.code || 0)
    if (!isTerminalStatus(jobStatus.value)) scheduleJobSync(300)
    if (closeCode !== 4001) return
    try {
      await axios.post('/api/v1/auth/refresh')
      openWs()
    } catch {}
  }
  ws.onerror = () => {
    if (!isTerminalStatus(jobStatus.value)) scheduleJobSync(300)
  }
}

const closeWs = () => {
  if (ws) {
    try {
      ws.close()
    } catch (e) {}
    ws = null
  }
}

const startJob = async () => {
  if (!selectedDeviceIds.value || selectedDeviceIds.value.length === 0) return
  const payload = {
    title: String(title.value || '').trim() || null,
    device_ids: selectedDeviceIds.value,
    commands_text: String(commandsText.value || ''),
  }
  running.value = true
  jobStatus.value = 'pending'
  lastId.value = '0-0'
  try {
    const res = await axios.post('/api/v1/config-push/jobs', payload)
    const jid = res?.data?.data?.job_id
    if (!jid) {
      running.value = false
      return
    }
    jobId.value = Number(jid)
    jobStatus.value = String(res?.data?.data?.status || 'pending')
    for (const d of selectedDevices.value) {
      ensureDeviceState(String(d.id))
    }
    activeTab.value = selectedDevices.value.length > 0 ? String(selectedDevices.value[0].id) : ''
    openWs()
    scheduleJobSync(500)
  } catch (e) {
    let msg = '创建任务失败'
    try {
      msg = e?.response?.data?.message || msg
    } catch {}
    ElNotification({ title: '配置下发', message: msg, type: 'error' })
    running.value = false
  }
}

const cancelJob = async () => {
  if (!jobId.value) return
  try {
    await axios.post(`/api/v1/config-push/jobs/${jobId.value}/cancel`)
    jobStatus.value = 'canceling'
    scheduleJobSync(300)
  } catch (e) {}
}

const resetAll = () => {
  closeWs()
  stopSyncTimer()
  title.value = ''
  commandsText.value = ''
  jobId.value = null
  jobStatus.value = ''
  lastId.value = '0-0'
  activeTab.value = ''
  running.value = false
  Object.keys(deviceState).forEach(k => delete deviceState[k])
}

const handleFileChange = async (file) => {
  const raw = file?.raw
  if (!raw) return
  try {
    const text = await raw.text()
    commandsText.value = String(text || '')
  } catch (e) {}
}

onMounted(async () => {
  window.addEventListener('resize', checkMobile)
  try {
    const res = await axios.get('/api/v1/user/device/get')
    devices.value = Array.isArray(res?.data) ? res.data : (Array.isArray(res?.data?.data) ? res.data.data : [])
  } catch (e) {
    devices.value = []
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
  stopSyncTimer()
  closeWs()
})
</script>

<style scoped>
.page {
  width: 100%;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.page.is-mobile {
  padding: 8px;
}

.card {
  width: 100%;
  height: calc(100vh - 32px);
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.page.is-mobile .card {
  height: calc(100vh - 16px);
}

/* Ensure card body takes remaining space if needed, though el-card structure is specific */
.card :deep(.el-card__body) {
  flex: 1;
  overflow: auto;
  display: flex;
  flex-direction: column;
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.tags-group {
  display: flex;
  align-items: center;
  gap: 6px;
}

.title {
  font-size: 16px;
  font-weight: 600;
  white-space: nowrap;
}

.job-tag {
  margin-left: 0;
}

.outputs {
  margin-top: 12px;
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0; /* important for flex nesting */
}

.device-tabs {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.device-tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow: auto;
  padding: 12px;
}

.output-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.meta-text {
  color: #666;
  font-size: 14px;
}

.output-box {
  width: 100%;
  min-height: 320px;
  background: #0b1020;
  color: #d1d5db;
  padding: 12px;
  border-radius: 6px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New', monospace;
  font-size: 13px;
  line-height: 1.5;
}

/* Mobile Styles */
@media (max-width: 768px) {
  .header {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .header-actions {
    width: 100%;
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
  }

  .header-left {
    width: 100%;
    justify-content: space-between;
  }
  
  .tags-group {
    margin-top: 0;
  }

  .output-box {
    font-size: 12px;
    padding: 8px;
    min-height: 200px;
  }
  
  .card :deep(.el-card__header) {
    padding: 10px;
  }
  
  .card :deep(.el-card__body) {
    padding: 10px;
  }
}
</style>
