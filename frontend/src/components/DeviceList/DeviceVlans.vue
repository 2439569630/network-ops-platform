<template>
  <div class="device-vlans">
    <el-card shadow="never" class="vlan-card">
      <template #header>
        <div class="card-header">
          <span class="title">VLAN 信息</span>
          <div>
            <el-button type="success" size="small" :loading="syncing" @click="handleSync" style="margin-right: 8px">从设备同步</el-button>
            <el-button type="primary" size="small" @click="fetchVlans">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="vlans" style="width: 100%" v-loading="loading">
        <el-table-column prop="vlan_id" label="VLAN ID" width="100" sortable />
        <el-table-column prop="name" label="名称" width="150" />
        <el-table-column prop="status" label="状态" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="row.status === 'active' ? 'success' : 'info'">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" />
        <el-table-column prop="ports" label="包含端口" min-width="200">
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
        </el-table-column>
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
const vlans = ref([])

const fetchVlans = async () => {
  if (!props.deviceId) return
  loading.value = true
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
    

    vlans.value = rawList.map(item => ({
      vlan_id: item.vlan_id || 0,
      name: item.name || `VLAN${item.vlan_id}`, // 有些设备可能没有 VLAN 名称
      status: (item.status || 'active').toLowerCase(),
      description: item.description || item.type || '',
      ports: Array.isArray(item.ports) ? item.ports : []
    }))
  } catch (error) {
    ElMessage.error('获取VLAN列表失败')
    vlans.value = []
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
  fetchVlans()
})
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
