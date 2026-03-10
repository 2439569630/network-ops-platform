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

        <div class="section-title">循环任务</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="指标巡检周期（秒）" prop="metrics_interval">
              <el-input-number v-model="form.metrics_interval" :min="-1" :max="3600" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">CPU/内存/磁盘/在线状态等基础指标巡检（默认 60 秒）</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />
        
        <div class="section-title">连接与超时</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="连接超时（秒）" prop="connect_timeout">
              <el-input-number v-model="form.connect_timeout" :min="1" :max="60" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">建立 SSH TCP 连接的最大等待时间</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="认证超时（秒）" prop="auth_timeout">
              <el-input-number v-model="form.auth_timeout" :min="1" :max="60" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">SSH 认证阶段的最大等待时间</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="Banner 超时（秒）" prop="banner_timeout">
              <el-input-number v-model="form.banner_timeout" :min="1" :max="300" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">等待设备返回登录 Banner/提示信息的超时</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="全局延迟因子" prop="global_delay_factor">
              <el-input-number v-model="form.global_delay_factor" :min="0.1" :max="10" :step="0.1" :precision="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">用于放大命令交互等待时间（设备响应慢时可适当调大）</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />

        <div class="section-title">深度巡检</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="深度巡检总间隔（秒）" prop="resource_sync_interval">
              <el-input-number v-model="form.resource_sync_interval" :min="-1" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">统一设置接口/路由/VLAN/插槽0接口详情的巡检频率（默认 3600 秒）；如下面单项填写，会覆盖该单项</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="接口同步间隔（秒）" prop="interfaces_sync_interval">
              <el-input-number v-model="form.interfaces_sync_interval" :min="-1" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">接口状态快检（up/down 等）</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="插槽0接口详情同步间隔（秒）" prop="interfaces_slot0_sync_interval">
              <el-input-number v-model="form.interfaces_slot0_sync_interval" :min="-1" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">深度查询插槽0接口详情</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="路由同步间隔（秒）" prop="routes_sync_interval">
              <el-input-number v-model="form.routes_sync_interval" :min="-1" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">定期同步路由表资源</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="VLAN 同步间隔（秒）" prop="vlans_sync_interval">
              <el-input-number v-model="form.vlans_sync_interval" :min="-1" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">定期同步 VLAN 资源</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />

        <div class="section-title">状态判定策略</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="离线判定阈值（次）" prop="offline_fail_threshold">
              <el-input-number v-model="form.offline_fail_threshold" :min="1" :max="10" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">状态机阈值：连续失败/采集无数据达到次数后判定离线；认证失败/不可达/超时等场景可能直接离线</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="恢复判定阈值（次）" prop="recovery_success_threshold">
              <el-input-number v-model="form.recovery_success_threshold" :min="1" :max="10" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">状态机阈值：离线后连续采集成功达到次数后恢复在线</div>
            </el-form-item>
          </el-col>
        </el-row>

        <el-divider />

        <div class="section-title">重试机制</div>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="最大重连次数" prop="connect_max_retries">
              <el-input-number v-model="form.connect_max_retries" :min="0" :max="5" :step="1" style="width: 100%" controls-position="right" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="重连等待时间（秒）" prop="connect_retry_delay_seconds">
              <el-input-number v-model="form.connect_retry_delay_seconds" :min="0" :max="60" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">连接失败后的等待时间（配合最大重连次数）</div>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="20">
          <el-col :span="12">
            <el-form-item label="离线重试间隔（秒）" prop="offline_retry_delay_seconds">
              <el-input-number v-model="form.offline_retry_delay_seconds" :min="0" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">设备离线后进入重试阶段的基础间隔</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="静默重试阈值" prop="offline_retry_silent_after_attempts">
              <el-input-number v-model="form.offline_retry_silent_after_attempts" :min="0" :max="999" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">达到次数后进入静默重试；0 表示关闭静默</div>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="静默最小间隔（秒）" prop="offline_retry_silent_min_interval_seconds">
              <el-input-number v-model="form.offline_retry_silent_min_interval_seconds" :min="0" :max="86400" :step="1" style="width: 100%" controls-position="right" />
              <div class="form-tip">静默期间的最小重试间隔（避免频繁重连）</div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, watch } from 'vue'
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
})

// 保存原始数据用于重置
let originalData = JSON.parse(JSON.stringify(form))

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
        return
      }
      if (key === 'metrics_interval' && data[key] === null) {
        form[key] = 0
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
.global-tip {
  margin-bottom: 16px;
}
.config-form {
  max-width: 920px;
}
</style>
