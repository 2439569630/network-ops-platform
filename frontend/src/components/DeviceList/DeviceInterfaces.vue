<template>
  <div class="device-interfaces">
    <el-card shadow="never" class="interface-card">
      <template #header>
        <div class="card-header">
          <span class="title">接口列表</span>
          <div>
            <el-button type="success" size="small" :loading="syncing" @click="handleSync" style="margin-right: 8px">从设备同步</el-button>
            <el-button type="primary" size="small" @click="fetchInterfaces">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="interfaces" style="width: 100%" v-loading="loading">
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
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
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
const interfaces = ref([])

const fetchInterfaces = async () => {
  if (!props.deviceId) return
  loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/interfaces/${props.deviceId}`)
    // 后端返回的结构可能需要适配
    // 假设后端返回: { name, phy_state, protocol_state, ... }
    // 我们需要映射到前端展示字段: name, status, ip_address, ...
    const rawList = Array.isArray(res?.data) ? res.data : (Array.isArray(res) ? res : [])
    
    interfaces.value = rawList.map(item => ({
      name: item.name || '',
      status: (item.protocol_state || item.phy_state || 'down').toLowerCase(),
      ip_address: item.ip_address || '-', // 待后端完善解析
      mac_address: item.mac_address || '-',
      speed: item.speed || '-',
      duplex: item.duplex || '-',
      description: item.description || ''
    }))
  } catch (error) {
    ElMessage.error('获取接口列表失败')
    interfaces.value = []
  } finally {
    loading.value = false
  }
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

onMounted(() => {
  fetchInterfaces()
})
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
</style>
