<template>
  <div class="device-alerts">
    <el-card shadow="never" class="alert-card">
      <template #header>
        <div class="card-header">
          <span class="title">预警规则</span>
          <el-button type="primary" size="small" @click="openAddDialog">添加规则</el-button>
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
        <el-table-column prop="message" label="内容" min-width="200" />
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
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="isEdit ? '编辑规则' : '添加规则'"
      width="500px"
      destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-form-item label="监控指标" prop="metric">
          <el-select v-model="form.metric" placeholder="请选择监控指标">
            <el-option label="CPU使用率" value="cpu_usage" />
            <el-option label="内存使用率" value="memory_usage" />
            <el-option label="磁盘使用率" value="disk_usage" />
            <el-option label="在线状态" value="online_status" />
          </el-select>
        </el-form-item>
        
        <el-form-item label="触发条件" required>
          <el-row :gutter="10">
            <el-col :span="10">
              <el-form-item prop="operator">
                <el-select v-model="form.operator" placeholder="条件">
                  <el-option label="大于" value=">" />
                  <el-option label="大于等于" value=">=" />
                  <el-option label="小于" value="<" />
                  <el-option label="小于等于" value="<=" />
                  <el-option label="等于" value="=" />
                </el-select>
              </el-form-item>
            </el-col>
            <el-col :span="14">
              <el-form-item prop="threshold">
                <el-input-number 
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
          <div class="form-tip">持续满足条件多少秒后触发告警，0表示即时触发</div>
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

const alertRules = ref([])
const alertLogs = ref([])

const form = reactive({
  id: null,
  metric: '',
  operator: '>',
  threshold: 80,
  severity: 'warning',
  duration: 0,
  is_enabled: true
})

const rules = {
  metric: [{ required: true, message: '请选择监控指标', trigger: 'change' }],
  operator: [{ required: true, message: '请选择条件', trigger: 'change' }],
  threshold: [{ required: true, message: '请输入阈值', trigger: 'blur' }],
  severity: [{ required: true, message: '请选择告警级别', trigger: 'change' }],
}

const getMetricLabel = (val) => {
  const map = { 
    cpu_usage: 'CPU使用率', 
    memory_usage: '内存使用率', 
    disk_usage: '磁盘使用率',
    online_status: '在线状态' 
  }
  return map[val] || val
}

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

const fetchLogs = async () => {
  if (!props.deviceId) return
  logsLoading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/alerts/logs/${props.deviceId}`)
    const rawData = res?.data || res
    alertLogs.value = Array.isArray(rawData) ? rawData : []
  } catch (error) {
    ElMessage.error('获取告警记录失败')
    alertLogs.value = []
  } finally {
    logsLoading.value = false
  }
}

const openAddDialog = () => {
  isEdit.value = false
  form.id = null
  form.metric = 'cpu_usage'
  form.operator = '>'
  form.threshold = 80
  form.severity = 'warning'
  form.duration = 60
  form.is_enabled = true
  dialogVisible.value = true
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

watch(() => props.deviceId, (newVal) => {
  if (newVal) {
    fetchRules()
    fetchLogs()
  }
}, { immediate: true })

onMounted(() => {
  if (props.deviceId) {
    fetchRules()
    fetchLogs()
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
.title {
  font-weight: 600;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 5px;
}
</style>
