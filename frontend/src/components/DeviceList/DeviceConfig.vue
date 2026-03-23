<template>
  <div class="device-config">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-header">
          <div class="title-wrap">
            <span class="title">监控参数配置</span>
            <span class="subtitle">状态监控与告警模块</span>
          </div>
          <div class="actions">
            <el-radio-group v-model="displayMode" size="small" class="mode-switch">
              <el-radio-button label="basic">基础模式</el-radio-button>
              <el-radio-button label="advanced">高级模式</el-radio-button>
            </el-radio-group>
            <el-button @click="resetForm">重置</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
          </div>
        </div>
      </template>

      <el-form 
        ref="formRef" 
        :model="form" 
        label-width="170px" 
        v-loading="loading"
        class="config-form"
      >
        <el-alert
          type="info"
          show-icon
          :closable="false"
          class="global-tip"
          title="间隔类字段说明"
        >
          <div>输入 -1 表示停用任务；输入 0 表示使用默认（保存后会回显为默认值）；输入 &gt;0 表示自定义秒数。</div>
        </el-alert>

        <div v-for="group in renderedGroups" :key="group" class="group-block">
          <div class="section-title">{{ getGroupLabel(group) }}</div>

          <el-row v-if="group !== 'alert_notification'" :gutter="16">
            <el-col v-for="field in (visibleFieldsByGroup[group] || [])" :key="field" :xs="24" :sm="24" :md="12" :lg="12">
              <el-form-item :label="getFieldLabel(field)" :prop="field">
                <el-input-number
                  v-model="form[field]"
                  v-bind="getFieldNumberProps(field)"
                  style="width: 100%"
                  controls-position="right"
                />
                <div v-if="getFieldTip(field)" class="form-tip">{{ getFieldTip(field) }}</div>
              </el-form-item>
            </el-col>
          </el-row>

          <div v-else class="notify-panel">
            <div class="notify-item" :class="siteCapability.available ? 'is-ok' : 'is-warn'">
              <span class="notify-label">站内通知</span>
              <span class="notify-text">{{ siteCapability.note || (siteCapability.available ? '已实现并默认可用' : '当前不可用') }}</span>
            </div>
            <div class="notify-item" :class="emailCapability.available ? 'is-ok' : 'is-warn'">
              <span class="notify-label">邮件通知</span>
              <span class="notify-text">{{ emailCapability.note || '需在系统配置中启用并完成邮件服务配置后生效' }}</span>
            </div>
            <div v-if="!emailCapability.available && emailUnreadyReasons.length" class="notify-reasons">
              不可用原因：{{ emailUnreadyReasons.join('；') }}
            </div>
            <el-button type="primary" plain class="notify-entry-btn" @click="goToAlertSubscription">前往告警订阅入口</el-button>
          </div>
          <el-divider v-if="group !== renderedGroups[renderedGroups.length - 1]" />
        </div>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, watch, computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import axios from '@/axios/axios'

const props = defineProps({
  deviceId: {
    type: [Number, String],
    default: null
  }
})

const loading = ref(false)
const saving = ref(false)
const formRef = ref(null)
const displayMode = ref('basic')
const route = useRoute()
const router = useRouter()
const configMeta = ref(null)
const capabilities = ref({ site: {}, email: {} })

const DEFAULT_FORM = {
  metrics_interval: 60,
  connect_timeout: 10,
  auth_timeout: 10,
  banner_timeout: 15,
  global_delay_factor: 2.0,
  offline_fail_threshold: 3,
  recovery_success_threshold: 2,
  connect_max_retries: 3,
  connect_retry_delay_seconds: 1.0,
  offline_retry_delay_seconds: 30.0,
  offline_retry_silent_after_attempts: 0,
  offline_retry_silent_min_interval_seconds: 300.0,
  resource_sync_interval: 3600.0,
  interfaces_sync_interval: 3600.0,
  interfaces_slot0_sync_interval: 3600.0,
  routes_sync_interval: 3600.0,
  vlans_sync_interval: 3600.0,
}

const FALLBACK_META = {
  group_labels: {
    basic_monitoring: '基础监控配置',
    resource_sync: '资源同步配置',
    state_recovery_policy: '状态判定与重连策略',
    alert_notification: '告警与通知配置',
  },
  basic_fields: ['metrics_interval', 'connect_timeout', 'offline_fail_threshold', 'recovery_success_threshold'],
  all_fields: Object.keys(DEFAULT_FORM),
  fields: {
    metrics_interval: { label: '指标监控周期（秒）', group: 'basic_monitoring', advanced: false },
    connect_timeout: { label: '连接超时（秒）', group: 'basic_monitoring', advanced: false },
    auth_timeout: { label: '认证超时（秒）', group: 'basic_monitoring', advanced: true },
    banner_timeout: { label: 'Banner 超时（秒）', group: 'basic_monitoring', advanced: true },
    global_delay_factor: { label: '全局延迟因子', group: 'basic_monitoring', advanced: true },
    resource_sync_interval: { label: '资源同步总间隔（秒）', group: 'resource_sync', advanced: true },
    interfaces_sync_interval: { label: '接口同步间隔（秒）', group: 'resource_sync', advanced: true },
    interfaces_slot0_sync_interval: { label: '插槽0接口详情同步间隔（秒）', group: 'resource_sync', advanced: true },
    routes_sync_interval: { label: '路由同步间隔（秒）', group: 'resource_sync', advanced: true },
    vlans_sync_interval: { label: 'VLAN 同步间隔（秒）', group: 'resource_sync', advanced: true },
    offline_fail_threshold: { label: '离线判定阈值（次）', group: 'state_recovery_policy', advanced: false },
    recovery_success_threshold: { label: '恢复判定阈值（次）', group: 'state_recovery_policy', advanced: false },
    connect_max_retries: { label: '最大重连次数', group: 'state_recovery_policy', advanced: true },
    connect_retry_delay_seconds: { label: '重连等待时间（秒）', group: 'state_recovery_policy', advanced: true },
    offline_retry_delay_seconds: { label: '离线重试间隔（秒）', group: 'state_recovery_policy', advanced: true },
    offline_retry_silent_after_attempts: { label: '静默重试阈值', group: 'state_recovery_policy', advanced: true },
    offline_retry_silent_min_interval_seconds: { label: '静默最小间隔（秒）', group: 'state_recovery_policy', advanced: true },
  },
}

const FIELD_TIPS = {
  metrics_interval: 'CPU/内存/磁盘/在线状态等基础指标采集周期（默认 60 秒）',
  connect_timeout: '建立 SSH TCP 连接的最大等待时间',
  auth_timeout: 'SSH 认证阶段的最大等待时间',
  banner_timeout: '等待设备返回登录 Banner/提示信息的超时',
  global_delay_factor: '用于放大命令交互等待时间（设备响应慢时可适当调大）',
  resource_sync_interval: '统一设置接口/路由/VLAN/插槽0接口详情的同步频率（默认 3600 秒）；如下面单项填写，会覆盖该单项',
  interfaces_sync_interval: '接口状态快检（up/down 等）',
  interfaces_slot0_sync_interval: '深度查询插槽0接口详情',
  routes_sync_interval: '定期同步路由表资源',
  vlans_sync_interval: '定期同步 VLAN 资源',
  offline_fail_threshold: '状态判定阈值：checking/collecting连续失败达到阈值后转离线；认证失败或不可达等会直接离线',
  recovery_success_threshold: '恢复阈值：离线后进入recovering，连续成功达到阈值才恢复为在线',
  connect_max_retries: '连接阶段最多重连次数，超限后进入离线状态',
  connect_retry_delay_seconds: '连接失败后的重连等待时间（配合最大重连次数）',
  offline_retry_delay_seconds: '离线后的基础重连间隔，用于控制retrying节奏',
  offline_retry_silent_after_attempts: '达到次数后进入静默重试；0 表示关闭静默',
  offline_retry_silent_min_interval_seconds: '静默期间的最小重试间隔（避免频繁重连）',
}

const FIELD_NUMBER_PROPS = {
  metrics_interval: { min: -1, max: 3600, step: 1 },
  connect_timeout: { min: 1, max: 60, step: 1 },
  auth_timeout: { min: 1, max: 60, step: 1 },
  banner_timeout: { min: 1, max: 300, step: 1 },
  global_delay_factor: { min: 0.1, max: 10, step: 0.1, precision: 1 },
  offline_fail_threshold: { min: 1, max: 10, step: 1 },
  recovery_success_threshold: { min: 1, max: 10, step: 1 },
  connect_max_retries: { min: 0, max: 5, step: 1 },
  connect_retry_delay_seconds: { min: 0, max: 60, step: 1 },
  offline_retry_delay_seconds: { min: 0, max: 86400, step: 1 },
  offline_retry_silent_after_attempts: { min: 0, max: 999, step: 1 },
  offline_retry_silent_min_interval_seconds: { min: 0, max: 86400, step: 1 },
  resource_sync_interval: { min: -1, max: 86400, step: 1 },
  interfaces_sync_interval: { min: -1, max: 86400, step: 1 },
  interfaces_slot0_sync_interval: { min: -1, max: 86400, step: 1 },
  routes_sync_interval: { min: -1, max: 86400, step: 1 },
  vlans_sync_interval: { min: -1, max: 86400, step: 1 },
}

const GROUP_ORDER = ['basic_monitoring', 'resource_sync', 'state_recovery_policy', 'alert_notification']

const form = reactive({ ...DEFAULT_FORM })

let originalData = JSON.parse(JSON.stringify(form))

const effectiveMeta = computed(() => {
  const raw = configMeta.value || {}
  return {
    group_labels: { ...FALLBACK_META.group_labels, ...(raw.group_labels || {}) },
    basic_fields: Array.isArray(raw.basic_fields) && raw.basic_fields.length ? raw.basic_fields : FALLBACK_META.basic_fields,
    all_fields: Array.isArray(raw.all_fields) && raw.all_fields.length ? raw.all_fields : FALLBACK_META.all_fields,
    fields: { ...FALLBACK_META.fields, ...(raw.fields || {}) },
  }
})

const groupOrder = computed(() => GROUP_ORDER.filter(k => effectiveMeta.value.group_labels[k]))
const renderedGroups = computed(() => {
  return groupOrder.value.filter((group) => {
    if (group === 'alert_notification') return true
    return (visibleFieldsByGroup.value[group] || []).length > 0
  })
})

const siteCapability = computed(() => capabilities.value?.site || {})
const emailCapability = computed(() => capabilities.value?.email || {})

const emailUnreadyReasons = computed(() => {
  const email = emailCapability.value || {}
  const reasons = []
  const codes = Array.isArray(email.unavailable_reasons) ? email.unavailable_reasons : []
  if (!email.global_enabled) {
    if (email.global_block_reason === 'config_disabled') reasons.push('系统配置中 email_enabled 未开启')
  }
  if (Array.isArray(email.missing_dependencies) && email.missing_dependencies.length) {
    reasons.push(`SMTP 配置缺失：${email.missing_dependencies.join(', ')}`)
  }
  if (email.has_user_email === false) reasons.push('当前账号未设置邮箱')
  if (email.user_email_notify_enabled === false) reasons.push('当前账号未开启邮件订阅')
  if (email.has_email_subscription_channel === false) reasons.push('当前设备/位置/规则订阅未包含邮件渠道')
  if (codes.includes('subscription_missing_email_channel') && !reasons.includes('当前设备/位置/规则订阅未包含邮件渠道')) {
    reasons.push('当前设备/位置/规则订阅未包含邮件渠道')
  }
  return reasons
})

const visibleFieldsByGroup = computed(() => {
  const fields = effectiveMeta.value.fields || {}
  const all = Array.isArray(effectiveMeta.value.all_fields) ? effectiveMeta.value.all_fields : []
  const basicSet = new Set(effectiveMeta.value.basic_fields || [])
  const grouped = {
    basic_monitoring: [],
    resource_sync: [],
    state_recovery_policy: [],
    alert_notification: [],
  }
  all.forEach((key) => {
    const meta = fields[key] || {}
    const group = String(meta.group || '').trim()
    if (!grouped[group]) return
    const isBasic = basicSet.has(key)
    if (displayMode.value === 'basic' && !isBasic) return
    grouped[group].push(key)
  })
  return grouped
})

const GROUP_LABEL_OVERRIDES = {
  state_recovery_policy: '状态判定与重连策略',
}

const getGroupLabel = (group) => GROUP_LABEL_OVERRIDES[group] || effectiveMeta.value.group_labels[group] || group
const getFieldLabel = (field) => effectiveMeta.value.fields[field]?.label || field
const getFieldTip = (field) => FIELD_TIPS[field] || ''
const getFieldNumberProps = (field) => FIELD_NUMBER_PROPS[field] || { step: 1 }

const ensureFormFields = (keys) => {
  keys.forEach((key) => {
    if (!(key in form)) {
      form[key] = null
    }
  })
}

const applyFlatConfig = (data) => {
  const allFields = Array.isArray(effectiveMeta.value.all_fields) ? effectiveMeta.value.all_fields : Object.keys(form)
  ensureFormFields(allFields)
  allFields.forEach((key) => {
    if (data?.[key] !== null && data?.[key] !== undefined) {
      form[key] = data[key]
      return
    }
    if (key === 'metrics_interval' && data?.[key] === null) {
      form[key] = 0
    }
  })
  originalData = JSON.parse(JSON.stringify(form))
}

const fetchConfig = async () => {
  if (!props.deviceId) return
  loading.value = true
  try {
    const [metaRes, groupedRes, capRes] = await Promise.allSettled([
      axios.get('/api/v1/user/device/config/meta'),
      axios.get(`/api/v1/user/device/config/grouped/${props.deviceId}`),
      axios.get('/api/v1/user/device/config/capabilities', { params: { device_id: props.deviceId } }),
    ])

    if (metaRes.status === 'fulfilled') {
      configMeta.value = metaRes.value?.data?.data || null
    }

    if (groupedRes.status === 'fulfilled') {
      const groupedData = groupedRes.value?.data?.data || {}
      const flat = groupedData.flat || {}
      if (groupedData.meta) {
        configMeta.value = groupedData.meta
      }
      if (groupedData.capabilities) {
        capabilities.value = groupedData.capabilities
      }
      applyFlatConfig(flat)
      return
    }

    if (capRes.status === 'fulfilled') {
      capabilities.value = capRes.value?.data?.data || { site: {}, email: {} }
    }

    const fallback = await axios.get(`/api/v1/user/device/config/${props.deviceId}`)
    const data = fallback?.data?.data || {}
    applyFlatConfig(data)
  } catch (error) {
    ElMessage.error('获取配置失败')
  } finally {
    loading.value = false
  }
}

const handleSave = async () => {
  if (!props.deviceId) return
  saving.value = true
  try {
    await axios.post('/api/v1/user/device/config/update', {
      device_id: props.deviceId,
      ...form
    })
    ElMessage.success('配置已保存并生效')
    originalData = JSON.parse(JSON.stringify(form))
  } catch (error) {
    ElMessage.error('保存配置失败')
  } finally {
    saving.value = false
  }
}

const resetForm = () => {
  Object.assign(form, originalData)
  ElMessage.info('已重置为上次保存的配置')
}

const goToAlertSubscription = () => {
  const nextQuery = { ...route.query, tab: 'alerts' }
  router.replace({ query: nextQuery })
}

watch(() => props.deviceId, (newVal) => {
  if (newVal) {
    fetchConfig()
  }
}, { immediate: true })
</script>

<style scoped>
.device-config {
  margin-top: 0;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.title {
  font-weight: 600;
}
.title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}
.subtitle {
  color: #909399;
  font-size: 12px;
  font-weight: 400;
}
.actions {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 12px;
  border-left: 4px solid #409eff;
  padding-left: 10px;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 5px;
}
.global-tip {
  margin-bottom: 12px;
}
.config-form {
  max-width: 1180px;
  margin: 0 auto;
}
.notify-tip {
  margin-bottom: 12px;
}
.mode-switch {
  margin-right: 8px;
}
.group-block {
  margin-bottom: 8px;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 12px 14px 6px;
  background: #fff;
}
.group-block :deep(.el-form-item) {
  margin-bottom: 14px;
}
.group-block :deep(.el-divider--horizontal) {
  margin: 8px 0 4px;
}
.notify-panel {
  display: grid;
  gap: 8px;
}
.notify-item {
  display: flex;
  align-items: center;
  gap: 10px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 8px 10px;
}
.notify-item.is-ok {
  border-color: rgba(103, 194, 58, 0.35);
  background: rgba(103, 194, 58, 0.08);
}
.notify-item.is-warn {
  border-color: rgba(230, 162, 60, 0.35);
  background: rgba(230, 162, 60, 0.08);
}
.notify-label {
  color: #303133;
  font-weight: 600;
  min-width: 70px;
}
.notify-text {
  color: #606266;
  font-size: 13px;
}
.notify-reasons {
  color: #e6a23c;
  font-size: 12px;
  line-height: 1.5;
}
.notify-entry-btn {
  width: fit-content;
}
</style>
