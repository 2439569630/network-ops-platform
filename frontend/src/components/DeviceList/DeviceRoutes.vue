<template>
  <div class="device-routes">
    <el-card shadow="never" class="route-card">
      <template #header>
        <div class="card-header">
          <span class="title">路由表</span>
          <div>
            <el-button type="success" size="small" :loading="syncing" @click="handleSync" style="margin-right: 8px">从设备同步</el-button>
            <el-button type="primary" size="small" @click="fetchRoutes">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table :data="routes" style="width: 100%" v-loading="loading">
        <el-table-column prop="destination" label="目的网络" min-width="140" />
        <el-table-column prop="mask" label="掩码" width="120" />
        <el-table-column prop="gateway" label="下一跳" min-width="140" />
        <el-table-column prop="interface" label="出接口" min-width="120" />
        <el-table-column prop="protocol" label="协议" width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="getProtocolType(row.protocol)">{{ row.protocol }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="metric" label="Metric" width="80" />
        <el-table-column prop="updated_at" label="更新时间" width="180" />
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
const routes = ref([])

const getProtocolType = (proto) => {
  const p = (proto || '').toLowerCase()
  if (p === 'direct') return 'success'
  if (p === 'static') return 'info'
  if (p.includes('ospf')) return 'warning'
  if (p.includes('bgp')) return 'danger'
  return ''
}

const fetchRoutes = async () => {
  if (!props.deviceId) return
  loading.value = true
  try {
    const res = await axios.get(`/api/v1/user/device/routes/${props.deviceId}`)
    // 后端返回 JSON 列表，字段映射需要根据 netmiko/huawei 解析结果调整
    
    let rawList = []
    if (res?.data?.data && Array.isArray(res.data.data)) {
        rawList = res.data.data
    } else if (Array.isArray(res?.data)) {
        rawList = res.data
    } else if (Array.isArray(res)) {
        rawList = res
    }
    
    routes.value = rawList.map(item => ({
      destination: item.destination || item.network || '',
      mask: item.mask || item.netmask || '',
      gateway: item.nexthop || item.gateway || item.next_hop || '-',
      interface: item.interface || '-',
      protocol: item.protocol || item.proto || 'Unknown',
      metric: item.metric || item.cost || 0,
      updated_at: item.updated_at || '-' // 路由表通常没有单条路由的时间戳，除非存库时加了
    }))
  } catch (error) {
    ElMessage.error('获取路由表失败')
    routes.value = []
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
  fetchRoutes()
})
</script>

<style scoped>
.device-routes {
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
