<template>
  <div :class="$style.container" v-loading="loading" element-loading-text="加载中...">
    <div :class="$style.header">
      <el-button :icon="ArrowLeft" @click="goBack">返回</el-button>
      <div :class="$style.titleWrap">
        <div :class="$style.title">{{ detail.device_name || '设备详情' }}</div>
        <el-tag
          :type="statusTagType"
          size="small"
          effect="dark"
        >
          {{ statusText }}
        </el-tag>
      </div>
      <div :class="$style.headerActions">
        <el-button v-if="canEdit" type="primary" @click="openEdit">编辑</el-button>
        <el-button v-if="canDelete" type="danger" @click="confirmDelete">删除</el-button>
      </div>
    </div>

    <div :class="$style.content">
      <el-tabs v-model="activeTab" :class="$style.tabs">
        <el-tab-pane label="概览" name="overview">
          <el-card :class="$style.section" shadow="never">
            <template #header>
              <div :class="$style.auditHeader">
                <div :class="$style.sectionHeader">状态</div>
              </div>
            </template>

            <div :class="$style.stats">
              <div :class="$style.statItem">
                <div :class="$style.statLabel">CPU</div>
                <div :class="$style.statValue">{{ formatPercent(detail.cpuUsage) }}</div>
                <el-progress :percentage="clampPercent(detail.cpuUsage)" :show-text="false" :stroke-width="8" />
              </div>
              <div :class="$style.statItem">
                <div :class="$style.statLabel">内存</div>
                <div :class="$style.statValue">{{ formatPercent(detail.memoryUsage) }}</div>
                <el-progress :percentage="clampPercent(detail.memoryUsage)" :show-text="false" :stroke-width="8" />
              </div>
              <div :class="$style.statItem">
                <div :class="$style.statLabel">磁盘</div>
                <div :class="$style.statValue">{{ formatPercent(detail.diskUsage) }}</div>
                <el-progress :percentage="clampPercent(detail.diskUsage)" :show-text="false" :stroke-width="8" />
              </div>
            </div>

            <div :class="$style.meta">
              <div :class="$style.metaItem">
                <span :class="$style.metaLabel">运行时长</span>
                <span :class="$style.metaValue">{{ detail.uptime || '未知' }}</span>
              </div>
              <div :class="$style.metaItem">
                <span :class="$style.metaLabel">系统版本</span>
                <span :class="$style.metaValue">{{ detail.osVersion || 'Unknown' }}</span>
              </div>
            </div>
          </el-card>

          <el-card :class="$style.section" shadow="never">
            <template #header>
              <div :class="$style.sectionHeader">基础信息</div>
            </template>

            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="设备名称">{{ detail.device_name || '-' }}</el-descriptions-item>
              <el-descriptions-item label="设备类型">{{ detail.type || '-' }}</el-descriptions-item>
              <el-descriptions-item label="IPv4">{{ detail.ipv4 || '-' }}</el-descriptions-item>
              <el-descriptions-item label="IPv6">{{ detail.ipv6 || '-' }}</el-descriptions-item>
              <el-descriptions-item label="MAC">{{ detail.mac || '-' }}</el-descriptions-item>
              <el-descriptions-item label="SSH端口">{{ detail.ssh_port || '-' }}</el-descriptions-item>
              <el-descriptions-item label="位置" :span="2">{{ detail.location || '-' }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 动态系统信息 -->
          <el-card 
            v-if="detail.vendor || detail.model || detail.version_raw" 
            :class="$style.section" 
            shadow="never"
          >
            <template #header>
              <div :class="$style.sectionHeader">系统信息</div>
            </template>

            <el-descriptions :column="2" border size="small">
              <el-descriptions-item v-if="detail.vendor" label="厂商">{{ detail.vendor }}</el-descriptions-item>
              <el-descriptions-item v-if="detail.model" label="型号">{{ detail.model }}</el-descriptions-item>
              <el-descriptions-item v-if="detail.product" label="产品系列">{{ detail.product }}</el-descriptions-item>
              <el-descriptions-item v-if="detail.version || detail.vrp_version" label="版本号">
                {{ detail.vrp_version || detail.version }}
              </el-descriptions-item>
            </el-descriptions>
            
            <div v-if="detail.version_raw" :class="$style.rawVersionBox">
              <div :class="$style.rawVersionTitle">原始版本信息</div>
              <pre :class="$style.rawVersionContent">{{ detail.version_raw }}</pre>
            </div>
          </el-card>

          <el-card :class="$style.section" shadow="never">
            <template #header>
              <div :class="$style.sectionHeader">归属信息</div>
            </template>

            <el-descriptions :column="2" border size="small">
              <el-descriptions-item label="添加人">{{ detail.created_by_name || '未知' }}</el-descriptions-item>
              <el-descriptions-item label="管理员">{{ detail.ops_admin_name || '未知' }}</el-descriptions-item>
            </el-descriptions>
          </el-card>
        </el-tab-pane>

        <el-tab-pane v-if="isNetworkDevice && canViewInterfaces" label="接口列表" name="interfaces">
          <DeviceInterfaces :device-id="deviceId" />
        </el-tab-pane>

        <el-tab-pane v-if="isNetworkDevice && canViewRoutes" label="路由表" name="routes">
          <DeviceRoutes :device-id="deviceId" />
        </el-tab-pane>

        <el-tab-pane v-if="isNetworkDevice && canViewVlans" label="VLAN" name="vlans">
          <DeviceVlans :device-id="deviceId" />
        </el-tab-pane>

        <el-tab-pane label="预警" name="alerts">
          <DeviceAlerts :device-id="deviceId" />
        </el-tab-pane>

        <el-tab-pane v-if="canEdit" label="配置" name="config">
          <DeviceConfig :device-id="deviceId" />
        </el-tab-pane>

        <el-tab-pane v-if="canAudit" label="审计" name="audit">
          <el-tabs v-model="auditTab" :class="$style.auditTabs">
            <el-tab-pane label="审计日志" name="operation">
              <el-card :class="$style.section" shadow="never" v-loading="auditLoading">
                <template #header>
                  <div :class="$style.auditHeader">
                    <div :class="$style.sectionHeader">审计日志</div>
                    <el-button size="small" @click="fetchAuditLogs">刷新</el-button>
                  </div>
                </template>

                <el-table :data="auditLogs" style="width: 100%">
                  <el-table-column type="expand">
                    <template #default="{ row }">
                      <div :class="$style.auditExpand">
                        <div :class="$style.auditExpandCol">
                          <div :class="$style.auditExpandTitle">旧值</div>
                          <pre :class="$style.auditJson">{{ formatJson(row.old_values) }}</pre>
                        </div>
                        <div :class="$style.auditExpandCol">
                          <div :class="$style.auditExpandTitle">新值</div>
                          <pre :class="$style.auditJson">{{ formatJson(row.new_values) }}</pre>
                        </div>
                      </div>
                    </template>
                  </el-table-column>
                  <el-table-column prop="changed_at" label="时间" width="190">
                    <template #default="{ row }">{{ formatDateTime(row.changed_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="change_type" label="类型" width="120" />
                  <el-table-column prop="changed_by_name" label="操作人" width="160">
                    <template #default="{ row }">{{ row.changed_by_name || row.changed_by || '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="change_description" label="描述" min-width="220" />
                </el-table>

                <div :class="$style.auditPager">
                  <el-pagination
                    v-model:current-page="auditPage"
                    v-model:page-size="auditPageSize"
                    :total="auditTotal"
                    layout="total, sizes, prev, pager, next"
                    :page-sizes="[10, 20, 50, 100, 200]"
                    @current-change="fetchAuditLogs"
                    @size-change="handleAuditSizeChange"
                  />
                </div>
              </el-card>
            </el-tab-pane>

            <el-tab-pane label="命令审计" name="command">
              <el-card :class="$style.section" shadow="never" v-loading="sshAuditLoading">
                <template #header>
                  <div :class="$style.auditHeader">
                    <div :class="$style.sectionHeader">命令审计</div>
                    <el-button size="small" @click="fetchSshAuditLogs">刷新</el-button>
                  </div>
                </template>

                <el-table :data="sshAuditLogs" style="width: 100%">
                  <el-table-column prop="executed_at" label="时间" width="190">
                    <template #default="{ row }">{{ formatDateTime(row.executed_at) }}</template>
                  </el-table-column>
                  <el-table-column prop="executed_by_name" label="操作人" width="160">
                    <template #default="{ row }">{{ row.executed_by_name || row.executed_by || '-' }}</template>
                  </el-table-column>
                  <el-table-column prop="command" label="命令" min-width="260" />
                </el-table>

                <div :class="$style.auditPager">
                  <el-pagination
                    v-model:current-page="sshAuditPage"
                    v-model:page-size="sshAuditPageSize"
                    :total="sshAuditTotal"
                    layout="total, sizes, prev, pager, next"
                    :page-sizes="[10, 20, 50, 100, 200]"
                    @current-change="fetchSshAuditLogs"
                    @size-change="handleSshAuditSizeChange"
                  />
                </div>
              </el-card>
            </el-tab-pane>
          </el-tabs>
        </el-tab-pane>
      </el-tabs>
    </div>

    <el-dialog v-model="editVisible" title="编辑设备" width="520px" destroy-on-close>
      <el-form :model="editForm" label-width="90px">
        <el-form-item label="设备名称">
          <el-input v-model="editForm.device_name" />
        </el-form-item>
        <el-form-item label="设备类型">
          <el-input v-model="editForm.type" />
        </el-form-item>
        <el-form-item label="位置">
          <el-input v-model="editForm.location" />
        </el-form-item>
        <el-form-item label="SSH端口">
          <el-input-number v-model="editForm.ssh_port" :min="1" :max="65535" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="saveEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import axios from '@/axios/axios'
import Cookies from 'js-cookie'
import { ElMessage, ElMessageBox } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'
import { getDeviceStatusTagType, getDeviceStatusText } from './deviceStatus'

import DeviceAlerts from './DeviceAlerts.vue'
import DeviceRoutes from './DeviceRoutes.vue'
import DeviceVlans from './DeviceVlans.vue'
import DeviceInterfaces from './DeviceInterfaces.vue'
import DeviceConfig from './DeviceConfig.vue'

const route = useRoute()
const router = useRouter()
const authStore = homeDataStore()
const nowTick = ref(Date.now())
let nowTimer = null

const deviceId = computed(() => {
  const raw = route.params.id
  const n = Number(raw)
  return Number.isFinite(n) ? n : null
})

const loading = ref(false)
const detail = reactive({
  id: null,
  device_name: '',
  type: '',
  ipv4: '',
  ipv6: '',
  mac: '',
  location: '',
  ssh_port: 22,
  created_by_name: '',
  ops_admin_name: '',
  status: 'offline',
  connectivity: 'offline',
  displayStatus: '',
  fsmState: '',
  fsmReason: '',
  cpuUsage: 0,
  memoryUsage: 0,
  diskUsage: 0,
  uptime: '未知',
  osVersion: 'Unknown',
  vendor: '',
  model: '',
  product: '',
  version: '',
  vrp_version: '',
  version_raw: '',
})

let ws = null

const canEdit = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:edit')))
const canDelete = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:del')))
const canAudit = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:audit')))
const canViewInterfaces = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:interface:view')))
const canViewRoutes = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:route:view')))
const canViewVlans = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:vlan:view')))

const isNetworkDevice = computed(() => {
  const t = String(detail.type || '').toLowerCase()
  return t.includes('switch') || 
         t.includes('router') || 
         t.includes('firewall') || 
         t.includes('交换机') || 
         t.includes('路由器') || 
         t.includes('防火墙')
})

const activeTab = computed({
  get() {
    const tab = String(route.query.tab || '')
    if (tab === 'audit' && canAudit.value) return 'audit'
    if (tab === 'alerts') return 'alerts'
    if (tab === 'interfaces' && canViewInterfaces.value) return 'interfaces'
    if (tab === 'routes' && canViewRoutes.value) return 'routes'
    if (tab === 'vlans' && canViewVlans.value) return 'vlans'
    if (tab === 'config' && canEdit.value) return 'config'
    return 'overview'
  },
  set(val) {
    const next = String(val || 'overview')
    const nextQuery = { ...route.query }
    if (next === 'audit') nextQuery.tab = 'audit'
    else if (next === 'alerts') nextQuery.tab = 'alerts'
    else if (next === 'config') nextQuery.tab = 'config'
    else if (['routes', 'vlans', 'interfaces'].includes(next)) nextQuery.tab = next
    else delete nextQuery.tab
    router.replace({ query: nextQuery })
  },
})

const editVisible = ref(false)
const editSaving = ref(false)
const editForm = reactive({
  device_name: '',
  type: '',
  location: '',
  ssh_port: 22,
})

const statusText = computed(() => getDeviceStatusText(detail, nowTick.value))

const statusTagType = computed(() => getDeviceStatusTagType(detail))

const clampPercent = (val) => {
  const n = Number(val)
  if (!Number.isFinite(n)) return 0
  if (n < 0) return 0
  if (n > 100) return 100
  return n
}

const formatPercent = (val) => `${clampPercent(val).toFixed(0)}%`

const applyStatusPayload = (payload) => {
  if (!payload || typeof payload !== 'object') return
  if (payload.status) detail.status = payload.status
  if (payload.connectivity) detail.connectivity = payload.connectivity
  if (payload.displayStatus) detail.displayStatus = payload.displayStatus
  if (payload.display_status) detail.displayStatus = payload.display_status
  if (payload.fsmState) detail.fsmState = payload.fsmState
  if (payload.fsm_state) detail.fsmState = payload.fsm_state
  if (payload.fsmReason) detail.fsmReason = payload.fsmReason
  if (payload.fsm_reason) detail.fsmReason = payload.fsm_reason
  
  if (payload.cpuUsage !== undefined) detail.cpuUsage = Number(payload.cpuUsage) || 0
  if (payload.memoryUsage !== undefined) detail.memoryUsage = Number(payload.memoryUsage) || 0
  if (payload.diskUsage !== undefined) detail.diskUsage = Number(payload.diskUsage) || 0
  if (payload.uptime) detail.uptime = payload.uptime
  if (payload.osVersion) detail.osVersion = payload.osVersion

  if (payload.vendor) detail.vendor = payload.vendor
  if (payload.model) detail.model = payload.model
  if (payload.product) detail.product = payload.product
  if (payload.version) detail.version = payload.version
  if (payload.vrp_version) detail.vrp_version = payload.vrp_version
  if (payload.version_raw) detail.version_raw = payload.version_raw
}

const openWs = () => {
  if (!deviceId.value) return
  const token = Cookies.get('token') || ''
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const url = `${proto}://${window.location.host}/api/v1/user/device/ws/detail/${deviceId.value}?token=${encodeURIComponent(token)}`
  ws = new WebSocket(url)
  ws.onmessage = (evt) => {
    try {
      const payload = JSON.parse(evt.data)
      applyStatusPayload(payload)
    } catch {}
  }
}

const closeWs = () => {
  try {
    if (ws) ws.close()
  } catch {}
  ws = null
}

const auditLoading = ref(false)
const auditLogs = ref([])
const auditTotal = ref(0)
const auditPage = ref(1)
const auditPageSize = ref(50)
const auditTab = ref('operation')

const sshAuditLoading = ref(false)
const sshAuditLogs = ref([])
const sshAuditTotal = ref(0)
const sshAuditPage = ref(1)
const sshAuditPageSize = ref(50)

const formatDateTime = (val) => {
  if (!val) return '-'
  const d = new Date(val)
  if (Number.isNaN(d.getTime())) return String(val)
  return d.toLocaleString()
}

const formatJson = (val) => {
  if (val === null || val === undefined || val === '') return '-'
  try {
    if (typeof val === 'string') {
      const s = val.trim()
      if (!s) return '-'
      if (s.startsWith('{') || s.startsWith('[')) return JSON.stringify(JSON.parse(s), null, 2)
      return s
    }
    return JSON.stringify(val, null, 2)
  } catch {
    return String(val)
  }
}

const fetchAuditLogs = async () => {
  if (!deviceId.value) return
  if (!canAudit.value) return
  auditLoading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/audit/logs/${deviceId.value}`, {
      params: { page: auditPage.value, page_size: auditPageSize.value },
    })
    const payload = res?.data || {}
    const data = payload?.data || payload
    auditLogs.value = Array.isArray(data?.items) ? data.items : []
    auditTotal.value = Number(data?.total || 0)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '获取审计日志失败')
  } finally {
    auditLoading.value = false
  }
}

const handleAuditSizeChange = async () => {
  auditPage.value = 1
  await fetchAuditLogs()
}

const fetchSshAuditLogs = async () => {
  if (!deviceId.value) return
  if (!canAudit.value) return
  sshAuditLoading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/audit/ssh-commands/${deviceId.value}`, {
      params: { page: sshAuditPage.value, page_size: sshAuditPageSize.value },
    })
    const payload = res?.data || {}
    const data = payload?.data || payload
    sshAuditLogs.value = Array.isArray(data?.items) ? data.items : []
    sshAuditTotal.value = Number(data?.total || 0)
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '获取命令审计失败')
  } finally {
    sshAuditLoading.value = false
  }
}

const handleSshAuditSizeChange = async () => {
  sshAuditPage.value = 1
  await fetchSshAuditLogs()
}

const fetchDetail = async () => {
  if (!deviceId.value) return
  loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/detail/${deviceId.value}`)
    const data = res?.data || {}
    detail.id = data.id ?? null
    detail.device_name = data.device_name || ''
    detail.type = data.type || data.device_type || ''
    detail.ipv4 = data.ipv4 || ''
    detail.ipv6 = data.ipv6 || ''
    detail.mac = data.mac || ''
    detail.location = data.location || ''
    detail.ssh_port = data.ssh_port || 22
    detail.created_by_name = data.created_by_name || ''
    detail.ops_admin_name = data.ops_admin_name || ''
    applyStatusPayload(data)
  } finally {
    loading.value = false
  }
}

const openEdit = () => {
  editForm.device_name = detail.device_name || ''
  editForm.type = detail.type || ''
  editForm.location = detail.location || ''
  editForm.ssh_port = Number(detail.ssh_port || 22)
  editVisible.value = true
}

const saveEdit = async () => {
  if (!deviceId.value) return
  editSaving.value = true
  try {
    await axios.post('/api/v1/user/device/update', {
      device_id: deviceId.value,
      device_name: editForm.device_name,
      type: editForm.type,
      location: editForm.location,
      ssh_port: editForm.ssh_port,
    })
    editVisible.value = false
    await fetchDetail()
    ElMessage.success('保存成功')
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '保存失败')
  } finally {
    editSaving.value = false
  }
}

const confirmDelete = async () => {
  if (!deviceId.value) return
  try {
    await ElMessageBox.confirm('确定要删除该设备吗？删除后将移入回收站', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await axios.post('/api/v1/user/device/delete', { id: deviceId.value })
    ElMessage.success('已移入回收站')
    router.push({ name: 'device' })
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '删除失败')
  }
}

const goBack = () => {
  router.back()
}

onMounted(async () => {
  authStore.syncAuthFromToken()
  await authStore.fetchPermissions()
  nowTimer = window.setInterval(() => {
    nowTick.value = Date.now()
  }, 1000)
  if (route.query.tab === 'audit' && !canAudit.value) {
    const nextQuery = { ...route.query }
    delete nextQuery.tab
    router.replace({ query: nextQuery })
  }
  await fetchDetail()
  try {
    await boostMonitor()
  } catch {}
  openWs()
})

onBeforeUnmount(async () => {
  if (nowTimer) {
    clearInterval(nowTimer)
    nowTimer = null
  }
  closeWs()
  try {
    await restoreMonitor()
  } catch {}
})

watch(
  () => activeTab.value,
  async (tab) => {
    if (tab !== 'audit') return
    if (auditTab.value === 'command') await fetchSshAuditLogs()
    else await fetchAuditLogs()
  },
  { immediate: true }
)

watch(
  () => auditTab.value,
  async () => {
    if (activeTab.value !== 'audit') return
    if (auditTab.value === 'command') await fetchSshAuditLogs()
    else await fetchAuditLogs()
  }
)
</script>

<style module>
.container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f0f2f5;
  padding: 20px;
  box-sizing: border-box;
  overflow: auto;
}

.header {
  display: flex;
  align-items: center;
  gap: 12px;
  background: #fff;
  padding: 14px 16px;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

.titleWrap {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.title {
  font-weight: 600;
  font-size: 16px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 320px;
}

.headerActions {
  margin-left: auto;
  display: flex;
  gap: 10px;
}

.content {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.tabs :global(.el-tabs__header) {
  margin: 0 0 12px 0;
}

.section {
  border-radius: 8px;
  border: none;
}

.sectionHeader {
  font-weight: 600;
}

.auditHeader {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.auditTabs :global(.el-tabs__header) {
  margin: 0 0 12px 0;
}

.auditPager {
  margin-top: 14px;
  display: flex;
  justify-content: flex-end;
}

.auditExpand {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.auditExpandCol {
  min-width: 0;
}

.auditExpandTitle {
  font-weight: 600;
  margin-bottom: 6px;
}

.auditJson {
  margin: 0;
  padding: 10px;
  background: #f8f9fa;
  border: 1px solid rgba(220, 223, 230, 0.7);
  border-radius: 6px;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 320px;
  overflow: auto;
  font-size: 12px;
  line-height: 1.4;
}

.stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
}

.statItem {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 12px;
  border: 1px solid rgba(220, 223, 230, 0.5);
}

.statLabel {
  font-size: 12px;
  color: #909399;
}

.statValue {
  margin: 6px 0 10px;
  font-size: 18px;
  font-weight: 700;
  color: #303133;
}

.meta {
  margin-top: 12px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.metaItem {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid rgba(220, 223, 230, 0.5);
}

.metaLabel {
  color: #909399;
  font-size: 12px;
}

.metaValue {
  color: #303133;
  font-size: 13px;
  font-weight: 500;
  margin-left: 8px;
  max-width: 280px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.rawVersionBox {
  margin-top: 16px;
  background: #f8f9fa;
  border-radius: 6px;
  border: 1px solid rgba(220, 223, 230, 0.5);
  padding: 12px;
}

.rawVersionTitle {
  font-size: 12px;
  font-weight: 600;
  color: #606266;
  margin-bottom: 8px;
}

.rawVersionContent {
  margin: 0;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #303133;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 200px;
  overflow-y: auto;
}
</style>
