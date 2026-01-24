<template>
  <div class="device-config">
    <el-card shadow="never" class="config-card">
      <template #header>
        <div class="card-header">
          <span class="title">监控参数配置</span>
          <div class="actions">
            <el-button @click="resetForm">重置</el-button>
            <el-button type="primary" :loading="saving" @click="handleSave">保存配置</el-button>
          </div>
        </div>
      </template>

      <el-form 
        ref="formRef" 
        :model="form" 
        label-width="140px" 
        v-loading="loading"
        class="config-form"
      >
        <div class="section-title">频率设置</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="数据采集间隔" prop="interval">
              <el-input-number v-model="form.interval" :min="-1" :max="3600" :step="0.1" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
              <div class="form-tip">完整采集设备指标（CPU/内存等）的周期；0 表示不限制，-1 表示停止任务</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="在线检测间隔" prop="monitor_interval">
              <el-input-number v-model="form.monitor_interval" :min="-1" :max="300" :step="0.1" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
              <div class="form-tip">快速检测设备在线状态（Ping/TCP）的周期；0 表示不限制，-1 表示停止任务</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />
        
        <div class="section-title">连接与超时</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="连接超时" prop="connect_timeout">
              <el-input-number v-model="form.connect_timeout" :min="1" :max="60" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="认证超时" prop="auth_timeout">
              <el-input-number v-model="form.auth_timeout" :min="1" :max="60" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="全局延迟系数" prop="global_delay_factor">
              <el-input-number v-model="form.global_delay_factor" :min="0.1" :max="10" :step="0.1" style="width: 100%" />
              <div class="form-tip">针对慢速设备的网络延迟倍数，默认 1.0</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />

        <div class="section-title">深度巡检</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="接口同步间隔" prop="interfaces_sync_interval">
              <el-input-number v-model="form.interfaces_sync_interval" :min="-1" :max="86400" :step="0.1" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
              <div class="form-tip">接口状态快检（up/down 等）；0 表示不限制，-1 表示停止任务</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="插槽0接口详情同步间隔" prop="interfaces_slot0_sync_interval">
              <el-input-number v-model="form.interfaces_slot0_sync_interval" :min="-1" :max="86400" :step="0.1" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
              <div class="form-tip">深度查询插槽0接口详情；0 表示不限制，-1 表示停止任务</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="路由同步间隔" prop="routes_sync_interval">
              <el-input-number v-model="form.routes_sync_interval" :min="-1" :max="86400" :step="0.1" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
              <div class="form-tip">定期同步路由表资源；0 表示不限制，-1 表示停止任务</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="VLAN 同步间隔" prop="vlans_sync_interval">
              <el-input-number v-model="form.vlans_sync_interval" :min="-1" :max="86400" :step="0.1" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
              <div class="form-tip">定期同步 VLAN 资源；0 表示不限制，-1 表示停止任务</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />

        <div class="section-title">状态判定策略</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="离线判定阈值" prop="offline_fail_threshold">
              <el-input-number v-model="form.offline_fail_threshold" :min="1" :max="10" style="width: 100%">
                <template #append>次</template>
              </el-input-number>
              <div class="form-tip">连续失败多少次后标记为离线</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="恢复判定阈值" prop="recovery_success_threshold">
              <el-input-number v-model="form.recovery_success_threshold" :min="1" :max="10" style="width: 100%">
                <template #append>次</template>
              </el-input-number>
              <div class="form-tip">连续成功多少次后标记为在线</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />

        <div class="section-title">重试机制</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="最大重连次数" prop="connect_max_retries">
              <el-input-number v-model="form.connect_max_retries" :min="0" :max="5" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="重连等待时间" prop="connect_retry_delay_seconds">
              <el-input-number v-model="form.connect_retry_delay_seconds" :min="0" :max="60" style="width: 100%">
                <template #append>秒</template>
              </el-input-number>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, watch } from 'vue'
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

const form = reactive({
  interval: 60,
  monitor_interval: 10,
  connect_timeout: 10,
  auth_timeout: 10,
  banner_timeout: 15,
  global_delay_factor: 1.0,
  offline_fail_threshold: 3,
  recovery_success_threshold: 2,
  connect_max_retries: 3,
  connect_retry_delay_seconds: 1.0,
  offline_retry_delay_seconds: 30.0,
  resource_sync_interval: 3600.0,
  interfaces_sync_interval: 3600.0,
  interfaces_slot0_sync_interval: 3600.0,
  routes_sync_interval: 3600.0,
  vlans_sync_interval: 3600.0,
})

// 保存原始数据用于重置
let originalData = {}

const fetchConfig = async () => {
  if (!props.deviceId) return
  loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/config/${props.deviceId}`)
    const data = res?.data?.data || {}
    
    // 合并数据，如果后端返回null则使用默认值
    Object.keys(form).forEach(key => {
      if (data[key] !== null && data[key] !== undefined) {
        form[key] = data[key]
      }
    })
    
    // 保存快照
    originalData = JSON.parse(JSON.stringify(form))
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

watch(() => props.deviceId, (newVal) => {
  if (newVal) {
    fetchConfig()
  }
}, { immediate: true })

onMounted(() => {
  if (props.deviceId) {
    fetchConfig()
  }
})
</script>

<style scoped>
.device-config {
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
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 20px;
  border-left: 4px solid #409eff;
  padding-left: 10px;
}
.form-tip {
  font-size: 12px;
  color: #909399;
  line-height: 1.5;
  margin-top: 5px;
}
.config-form {
  max-width: 800px;
}
</style>
