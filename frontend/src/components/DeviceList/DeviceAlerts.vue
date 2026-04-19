<template>
  <div class="device-alerts">
    <el-card shadow="never" class="alert-card">
      <template #header>
        <div class="card-header">
          <span class="title">告警规则</span>
          <div class="header-actions">
            <!-- <el-dropdown trigger="click" @command="applyTemplate">
              <el-button size="small">添加模板</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="temp">温度模板（temperature）</el-dropdown-item>
                  <el-dropdown-item command="if_counts">接口模板（down计数）</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown> -->
            <el-button size="small" @click="openSubscriptionDialog">配置通知</el-button>
            <el-button type="primary" size="small" @click="openAddDialog">添加规则</el-button>
          </div>
        </div>
      </template>

      <el-table :data="alertRules" style="width: 100%" v-loading="loading">
        <el-table-column prop="metric" label="监控指标" width="150">
          <template #default="{ row }">
            {{ getMetricLabel(row.metric) }}
          </template>
        </el-table-column>
        <el-table-column prop="operator" label="触发条件" width="150">
          <template #default="{ row }">
            {{ getOperatorLabel(row.operator) }} {{ row.threshold }}{{ isPercentMetric(row.metric) ? '%' : '' }}
          </template>
        </el-table-column>
        <el-table-column prop="duration" label="持续时间" width="120">
          <template #default="{ row }">
            {{ row.duration > 0 ? `${row.duration}秒` : '即时' }}
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="告警级别" width="100">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)" size="small">
              {{ getSeverityLabel(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="is_enabled" label="启用状态" width="100">
          <template #default="{ row }">
            <el-switch 
              v-model="row.is_enabled" 
              size="small" 
              :loading="row.statusLoading"
              @change="handleStatusChange(row)" 
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="150">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click="handleEdit(row)">编辑</el-button>
            <el-button type="danger" link size="small" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="alert-card" style="margin-top: 20px;">
      <template #header>
        <div class="card-header">
          <span class="title">最近告警记录</span>
          <el-button type="default" size="small" :icon="Refresh" @click="fetchLogs">刷新</el-button>
        </div>
      </template>
      <el-table :data="alertLogs" style="width: 100%" v-loading="logsLoading">
        <el-table-column prop="triggered_at" label="时间" width="180">
          <template #default="{ row }">
            {{ formatTime(row.triggered_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="metric" label="指标" width="120">
          <template #default="{ row }">
            {{ getMetricLabel(row.metric) }}
          </template>
        </el-table-column>
        <el-table-column prop="message" label="内容" min-width="200">
          <template #default="{ row }">
            {{ formatAlertMessage(row.message) }}
          </template>
        </el-table-column>
        <el-table-column prop="severity" label="级别" width="100">
          <template #default="{ row }">
            <el-tag :type="getSeverityType(row.severity)" size="small">
              {{ getSeverityLabel(row.severity) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="resolved_at" label="状态" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.resolved_at" type="success" size="small">已恢复</el-tag>
            <el-tag v-else type="danger" size="small">未恢复</el-tag>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="currentPage"
          v-model:page-size="pageSize"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, prev, pager, next"
          @current-change="handlePageChange"
          @size-change="fetchLogs"
          small
          background
        />
      </div>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑规则' : '添加规则'"
      width="500px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="监控指标" prop="metric">
          <el-select
            v-model="form.metric"
            placeholder="请选择或输入监控指标"
            filterable
          >
            <el-option label="CPU 使用率" value="cpu_usage" />
            <el-option label="内存使用率" value="memory_usage" />
            <el-option label="磁盘使用率" value="disk_usage" />
            <el-option label="在线状态" value="online_status" />
            <el-option label="接口物理 Down 数" value="if_phy_down_count" />
            <el-option label="接口协议 Down 数" value="if_protocol_down_count" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="触发条件" required>
          <el-row :gutter="10">
            <el-col :span="10">
              <el-form-item prop="operator">
                <el-select v-if="form.metric !== 'online_status'" v-model="form.operator" placeholder="条件">
                  <el-option label="大于" value=">" />
                  <el-option label="大于等于" value=">=" />
                  <el-option label="小于" value="<" />
                  <el-option label="小于等于" value="<=" />
                  <el-option label="等于" value="=" />
                </el-select>
                <el-select v-else v-model="form.operator" placeholder="条件" disabled>
                  <el-option label="等于" value="=" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="14">
              <el-form-item prop="threshold">
                <el-select v-if="form.metric === 'online_status'" v-model="form.threshold" style="width: 100%">
                  <el-option label="离线(0)" :value="0" />
                  <el-option label="在线(1)" :value="1" />
                </el-select>
                <el-input-number
                  v-else
                  v-model="form.threshold"
                  :min="0"
                  style="width: 100%"
                  placeholder="阈值"
                  :controls="false"
                >
                  <template #append v-if="isPercentMetric(form.metric)">%</template>
                </el-input-number>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form-item>

        <el-form-item label="持续时间" prop="duration">
          <el-input-number v-model="form.duration" :min="0" style="width: 100%" placeholder="0表示即时触发">
            <template #append>秒</template>
          </el-input-number>
          <div class="form-tip">持续满足条件多少秒后触发告警，0表示即时触发；online_status 表示设备持续离线多少秒后告警</div>
        </el-form-item>

        <el-form-item label="告警级别" prop="severity">
          <el-select v-model="form.severity" placeholder="请选择告警级别">
            <el-option label="提示" value="info" />
            <el-option label="警告" value="warning" />
            <el-option label="严重" value="critical" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="启用状态" prop="is_enabled">
          <el-switch v-model="form.is_enabled" />
        </el-form-item>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="submitting" @click="handleSubmit">确定</el-button>
        </span>
      </template>
    </el-dialog>

    <el-dialog
      v-model="subscriptionDialogVisible"
      title="订阅设备告警通知"
      width="520px"
      destroy-on-close
    >
      <el-form label-width="100px">
        <el-form-item label="通知渠道">
          <el-checkbox-group v-model="subscriptionForm.channels">
            <el-checkbox label="site">站内消息</el-checkbox>
            <el-checkbox label="email">邮箱</el-checkbox>
          </el-checkbox-group>
          <div class="form-tip">站内通知已实现并默认可用</div>
          <div class="form-tip">邮件通知需在系统配置中启用并完成邮件服务配置后生效</div>
        </el-form-item>

        <el-form-item label="告警级别">
          <el-checkbox-group v-model="subscriptionForm.severities">
            <el-checkbox label="info">提示</el-checkbox>
            <el-checkbox label="warning">警告</el-checkbox>
            <el-checkbox label="critical">严重</el-checkbox>
          </el-checkbox-group>
          <div class="form-tip">不勾选表示订阅全部级别</div>
        </el-form-item>

        <el-form-item label="启用">
          <el-switch v-model="subscriptionForm.is_enabled" />
        </el-form-item>
      </el-form>

      <template #footer>
        <span class="dialog-footer">
          <el-button v-if="subscriptionForm.id" type="danger" plain :loading="subscriptionSubmitting" @click="deleteSubscription">取消订阅</el-button>
          <el-button @click="subscriptionDialogVisible = false">取消</el-button>
          <el-button type="primary" :loading="subscriptionSubmitting" @click="saveSubscription">保存</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import axios from '@/axios/axios'
import dayjs from 'dayjs'

const props = defineProps({
  deviceId: {
    type: [Number, String],
    default: null
  }
})

const loading = ref(false)
const logsLoading = ref(false)
const submitting = ref(false)
const dialogVisible = ref(false)
const isEdit = ref(false)
const formRef = ref(null)
const subscriptionDialogVisible = ref(false)
const subscriptionSubmitting = ref(false)

const alertRules = ref([])
const alertLogs = ref([])
const currentPage = ref(1)
const pageSize = ref(10)
const total = ref(0)

const form = reactive({
  id: null,
  metric: '',
  operator: '>',
  threshold: 80,
  severity: 'warning',
  duration: 0,
  is_enabled: true
})

const subscriptionForm = reactive({
  id: null,
  channels: ['site'],
  severities: [],
  is_enabled: true
})

const rules = {
  metric: [{ required: true, message: '请选择监控指标', trigger: 'change' }],
  operator: [{ required: true, message: '请选择条件', trigger: 'change' }],
  threshold: [{ required: true, message: '请输入阈值', trigger: 'blur' }],
  severity: [{ required: true, message: '请选择告警级别', trigger: 'change' }],
}

const humanizeMetricKey = (key) => {
  const raw = String(key || '').trim()
  if (!raw) return ''

  const tokenUpperMap = {
    cpu: 'CPU',
    ip: 'IP',
    ssh: 'SSH',
    snmp: 'SNMP',
    mac: 'MAC',
    vlan: 'VLAN',
    qos: 'QoS',
    poe: 'PoE',
    rx: 'RX',
    tx: 'TX',
    oid: 'OID',
  }

  const [base, suffix] = raw.split(':', 2)
  const words = String(base || '')
    .split('_')
    .map((w) => String(w || '').trim())
    .filter(Boolean)
    .map((w) => tokenUpperMap[w.toLowerCase()] || (w[0] ? w[0].toUpperCase() + w.slice(1).toLowerCase() : w))
    .join(' ')

  if (suffix) return `${words}（${suffix}）`
  return words
}

const formatMetric = (metric) => {
  const m = String(metric || '').trim()
  if (!m) return '-'

  if (m.startsWith('if_phy_down:')) {
    const iface = m.split(':', 2)[1] || ''
    return iface ? `接口物理 Down（${iface}）` : '接口物理 Down'
  }
  if (m.startsWith('if_protocol_down:')) {
    const iface = m.split(':', 2)[1] || ''
    return iface ? `接口协议 Down（${iface}）` : '接口协议 Down'
  }

  const map = {
    cpu_usage: 'CPU 使用率',
    memory_usage: '内存使用率',
    disk_usage: '磁盘使用率',
    online_status: '在线状态',
    if_phy_down_count: '接口物理 Down 数',
    if_protocol_down_count: '接口协议 Down 数',
  }
  return map[m] || humanizeMetricKey(m) || m
}

const getMetricLabel = (val) => formatMetric(val)

const getOperatorLabel = (val) => {
  const map = { '>': '>', '>=': '≥', '<': '<', '<=': '≤', '=': '=' }
  return map[val] || val
}

const getSeverityLabel = (val) => {
  const map = { info: '提示', warning: '警告', critical: '严重' }
  return map[val] || val
}

const getSeverityType = (val) => {
  const map = { info: 'info', warning: 'warning', critical: 'danger' }
  return map[val] || 'info'
}

const isPercentMetric = (metric) => {
  return ['cpu_usage', 'memory_usage', 'disk_usage'].includes(metric)
}

const formatTime = (time) => {
  if (!time) return '-'
  return dayjs(time).format('YYYY-MM-DD HH:mm:ss')
}

const formatOfflineReason = (reason) => {
  const raw = String(reason || '').trim()
  if (!raw) return ''
  const low = raw.toLowerCase()

  if (low.includes('timed out') || low.includes('timeout') || low.includes('read timeout') || low.includes('netmikotimeoutexception')) {
    return '连接超时'
  }
  if (
    low.includes('netmikoauthenticationexception') ||
    low.includes('authentication failed') ||
    low.includes('bad authentication type') ||
    low.includes('not allowed')
  ) {
    return '认证失败'
  }
  if (
    low.includes('connection refused') ||
    low.includes('no route to host') ||
    low.includes('name or service not known') ||
    low.includes('nodename nor servname') ||
    low.includes('unreachable')
  ) {
    return '不可达'
  }
  if (
    low.includes('connection reset by peer') ||
    low.includes('broken pipe') ||
    low.includes('socket is closed') ||
    low.includes('eoferror') ||
    low.includes('bad file descriptor')
  ) {
    return '连接中断'
  }

  const stripped = raw.replace(/^[A-Za-z_][A-Za-z0-9_]*?(Exception|Error):\s*/u, '').trim()
  return stripped || raw
}

const formatAlertMessage = (message) => {
  const raw = String(message || '').trim()
  if (!raw) return '-'

  const firingPrefix = '触发告警:'
  const resolvePrefix = '告警恢复:'
  const offlinePrefix = '设备离线:'

  if (raw.startsWith(firingPrefix)) {
    return raw.replace(/^触发告警:\s*([^\s]+)\s*/u, (_m, metric) => `触发告警: ${formatMetric(metric)} `).trim()
  }
  if (raw.startsWith(resolvePrefix)) {
    return raw.replace(/^告警恢复:\s*([^\s]+)\s*/u, (_m, metric) => `告警恢复: ${formatMetric(metric)} `).trim()
  }
  if (raw.startsWith(offlinePrefix)) {
    const reason = raw.slice(offlinePrefix.length).trim()
    const label = formatOfflineReason(reason)
    return label ? `设备离线: ${label}` : '设备离线'
  }

  return raw
}

const fetchRules = async () => {
  if (!props.deviceId) return
  loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/alerts/rules/${props.deviceId}`)
    const rawData = res?.data || res
    alertRules.value = Array.isArray(rawData) ? rawData : []
  } catch (error) {
    ElMessage.error('获取告警规则失败')
    alertRules.value = []
  } finally {
    loading.value = false
  }
}

const fetchDeviceSubscription = async () => {
  if (!props.deviceId) return
  try {
    const res = await axios.get('/api/v1/user/device/alerts/subscriptions', {
      params: { scope_type: 'device', scope_id: props.deviceId }
    })
    const rawData = res?.data || res
    const list = Array.isArray(rawData) ? rawData : []
    const sub = list.length ? list[0] : null
    if (sub) {
      subscriptionForm.id = sub.id
      subscriptionForm.channels = Array.isArray(sub.channels) && sub.channels.length ? sub.channels : ['site']
      subscriptionForm.severities = Array.isArray(sub.severities) ? sub.severities : []
      subscriptionForm.is_enabled = Boolean(sub.is_enabled)
    } else {
      subscriptionForm.id = null
      subscriptionForm.channels = ['site']
      subscriptionForm.severities = []
      subscriptionForm.is_enabled = true
    }
  } catch (e) {
    subscriptionForm.id = null
    subscriptionForm.channels = ['site']
    subscriptionForm.severities = []
    subscriptionForm.is_enabled = true
  }
}

const fetchLogs = async () => {
  if (!props.deviceId) return
  logsLoading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/alerts/logs/${props.deviceId}`, {
      params: {
        limit: pageSize.value,
        offset: (currentPage.value - 1) * pageSize.value
      }
    })
    const rawData = res?.data || res
    if (rawData && typeof rawData.total === 'number') {
      alertLogs.value = Array.isArray(rawData.items) ? rawData.items : []
      total.value = rawData.total
    } else {
      alertLogs.value = Array.isArray(rawData) ? rawData : []
      total.value = alertLogs.value.length
    }
  } catch (error) {
    ElMessage.error('获取告警记录失败')
    alertLogs.value = []
  } finally {
    logsLoading.value = false
  }
}

const handlePageChange = (page) => {
  currentPage.value = page
  fetchLogs()
}

const openAddDialog = () => {
  isEdit.value = false
  form.id = null
  form.metric = 'cpu_usage'
  form.operator = '>='
  form.threshold = 90
  form.severity = 'warning'
  form.duration = 300
  form.is_enabled = true
  dialogVisible.value = true
}

const openSubscriptionDialog = async () => {
  await fetchDeviceSubscription()
  subscriptionDialogVisible.value = true
}

const saveSubscription = async () => {
  if (!props.deviceId) return
  if (!Array.isArray(subscriptionForm.channels) || subscriptionForm.channels.length === 0) {
    ElMessage.error('请选择至少一个通知渠道')
    return
  }
  subscriptionSubmitting.value = true
  try {
    const payload = {
      channels: subscriptionForm.channels,
      severities: Array.isArray(subscriptionForm.severities) && subscriptionForm.severities.length ? subscriptionForm.severities : null,
      is_enabled: Boolean(subscriptionForm.is_enabled)
    }
    if (subscriptionForm.id) {
      await axios.put(`/api/v1/user/device/alerts/subscriptions/${subscriptionForm.id}`, payload)
    } else {
      await axios.post('/api/v1/user/device/alerts/subscriptions', {
        scope_type: 'device',
        scope_id: props.deviceId,
        ...payload
      })
    }
    ElMessage.success('订阅已保存')
    subscriptionDialogVisible.value = false
  } catch (e) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    subscriptionSubmitting.value = false
  }
}

const deleteSubscription = async () => {
  if (!subscriptionForm.id) return
  try {
    await ElMessageBox.confirm('确定要取消订阅吗？', '提示', { type: 'warning' })
    subscriptionSubmitting.value = true
    await axios.delete(`/api/v1/user/device/alerts/subscriptions/${subscriptionForm.id}`)
    ElMessage.success('已取消订阅')
    subscriptionDialogVisible.value = false
    subscriptionForm.id = null
    subscriptionForm.channels = ['site']
    subscriptionForm.severities = []
    subscriptionForm.is_enabled = true
  } catch (e) {
  } finally {
    subscriptionSubmitting.value = false
  }
}

const applyTemplate = async (name) => {
  if (!props.deviceId) return
  const templates = {
    if_counts: [
      { metric: 'if_phy_down_count', operator: '>', threshold: 0, severity: 'warning', duration: 60, is_enabled: true },
      { metric: 'if_protocol_down_count', operator: '>', threshold: 0, severity: 'warning', duration: 60, is_enabled: true },
    ],
  }
  const list = templates[String(name)] || []
  if (!list.length) return
  try {
    for (const r of list) {
      await axios.post('/api/v1/user/device/alerts/rules', { ...r, device_id: props.deviceId })
    }
    ElMessage.success('模板添加成功')
    fetchRules()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || '模板添加失败')
  }
}

const handleEdit = (row) => {
  isEdit.value = true
  Object.assign(form, row)
  dialogVisible.value = true
}

const handleDelete = (row) => {
  ElMessageBox.confirm('确定要删除这条规则吗？', '提示', {
    type: 'warning'
  }).then(async () => {
    try {
      await axios.delete(`/api/v1/user/device/alerts/rules/${row.id}`)
      ElMessage.success('删除成功')
      fetchRules()
    } catch (error) {
      ElMessage.error('删除失败')
    }
  }).catch(() => {})
}

const handleStatusChange = async (row) => {
  row.statusLoading = true
  try {
    await axios.put(`/api/v1/user/device/alerts/rules/${row.id}`, {
      is_enabled: row.is_enabled
    })
    ElMessage.success(`规则已${row.is_enabled ? '启用' : '禁用'}`)
  } catch (error) {
    row.is_enabled = !row.is_enabled // revert
    ElMessage.error('状态更新失败')
  } finally {
    row.statusLoading = false
  }
}

const handleSubmit = async () => {
  if (!formRef.value) return
  await formRef.value.validate(async (valid) => {
    if (valid) {
      submitting.value = true
      try {
        const payload = {
          ...form,
          device_id: props.deviceId
        }
        
        if (isEdit.value) {
          await axios.put(`/api/v1/user/device/alerts/rules/${form.id}`, payload)
          ElMessage.success('修改成功')
        } else {
          await axios.post('/api/v1/user/device/alerts/rules', payload)
          ElMessage.success('添加成功')
        }
        dialogVisible.value = false
        fetchRules()
      } catch (error) {
        ElMessage.error(error.response?.data?.detail || (isEdit.value ? '修改失败' : '添加失败'))
      } finally {
        submitting.value = false
      }
    }
  })
}

watch(
  () => form.metric,
  (val) => {
    if (String(val || '').trim() === 'online_status') {
      form.operator = '='
      if (form.threshold !== 0 && form.threshold !== 1) {
        form.threshold = 0
      }
    }
  }
)

watch(() => props.deviceId, (newVal) => {
  if (newVal) {
    fetchRules()
    fetchLogs()
    fetchDeviceSubscription()
  }
}, { immediate: true })

onMounted(() => {
  if (props.deviceId) {
    fetchRules()
    fetchLogs()
    fetchDeviceSubscription()
  }
})
</script>

<style scoped>
.device-alerts {
  margin-top: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 10px;
  align-items: center;
}
.title {
  font-weight: 600;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 5px;
}
.pagination-container {
  margin-top: 15px;
  display: flex;
  justify-content: flex-end;
}
</style>
