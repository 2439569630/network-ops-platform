<template>
  <div :class="$style.container" v-loading="loading" element-loading-text="加载中...">
    <div :class="$style.header">
      <el-button :icon="ArrowLeft" @click="goBack">返回</el-button>
      <div :class="$style.title">回收站</div>
      <div :class="$style.headerActions">
        <el-button :loading="loading" @click="fetchRecycleBin">刷新</el-button>
      </div>
    </div>

    <div :class="$style.content">
      <el-card :class="$style.section" shadow="never">
        <el-table :data="rows" style="width: 100%" v-loading="loading">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="device_name" label="设备名称" min-width="160" show-overflow-tooltip />
          <el-table-column prop="ipv4" label="IPv4" width="140" show-overflow-tooltip />
          <el-table-column prop="device_type" label="类型" width="120" show-overflow-tooltip />
          <el-table-column prop="location" label="位置" min-width="140" show-overflow-tooltip />
          <el-table-column prop="ssh_port" label="SSH端口" width="100" />
          <el-table-column label="删除时间" width="190">
            <template #default="scope">
              {{ formatDate(scope.row.deleted_at || scope.row.updated_at) }}
            </template>
          </el-table-column>
          <el-table-column prop="deleted_by" label="删除人" width="140" show-overflow-tooltip>
            <template #default="scope">
              {{ scope.row.deleted_by || scope.row.updated_by || '-' }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="180" fixed="right">
            <template #default="scope">
              <el-button link type="primary" :disabled="acting" @click="restoreDevice(scope.row)">恢复</el-button>
              <el-button link type="danger" :disabled="acting" @click="purgeDevice(scope.row)">彻底删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import axios from '@/axios/axios'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDeviceStore } from './store'

const router = useRouter()
const deviceStore = useDeviceStore()

const loading = ref(false)
const acting = ref(false)
const rows = ref([])

const formatDate = (val) => {
  if (!val) return '-'
  try {
    return new Date(val).toLocaleString()
  } catch {
    return String(val)
  }
}

const fetchRecycleBin = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/user/device/recycle/list')
    const data = res?.data || {}
    rows.value = Array.isArray(data.data) ? data.data : []
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '获取回收站失败')
  } finally {
    loading.value = false
  }
}

const restoreDevice = async (row) => {
  const id = row?.id
  if (!id) return
  try {
    await ElMessageBox.confirm('确定要恢复该设备吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  acting.value = true
  try {
    await axios.post('/api/v1/user/device/recycle/restore', { device_id: id })
    ElMessage.success('恢复成功')
    await fetchRecycleBin()
    deviceStore.refreshData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '恢复失败')
  } finally {
    acting.value = false
  }
}

const purgeDevice = async (row) => {
  const id = row?.id
  if (!id) return
  try {
    await ElMessageBox.confirm('确定要彻底删除该设备吗？此操作不可恢复', '警告', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
  } catch {
    return
  }
  acting.value = true
  try {
    await axios.post('/api/v1/user/device/recycle/purge', { device_id: id })
    ElMessage.success('已彻底删除')
    await fetchRecycleBin()
    deviceStore.refreshData()
  } catch (e) {
    ElMessage.error(e?.response?.data?.message || e?.message || '删除失败')
  } finally {
    acting.value = false
  }
}

const goBack = () => {
  router.push({ name: 'device' })
}

onMounted(async () => {
  await fetchRecycleBin()
})
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

.title {
  font-weight: 600;
  font-size: 16px;
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

.section {
  border-radius: 8px;
  border: none;
}
</style>

