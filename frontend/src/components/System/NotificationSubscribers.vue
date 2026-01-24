<template>
  <div class="notification-subscribers">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="title">预警通知订阅</span>
          <el-button :icon="Refresh" circle @click="fetchData" />
        </div>
      </template>
      
      <el-table :data="tableData" v-loading="loading" style="width: 100%">
        <el-table-column prop="username" label="用户名" width="150" />
        <el-table-column prop="nickname" label="昵称" width="150" />
        <el-table-column prop="email" label="邮箱" min-width="200" />
        <el-table-column label="订阅状态" width="150">
          <template #default="{ row }">
            <el-switch
              v-model="row.is_email_notify"
              :loading="row.loading"
              :disabled="row.id !== currentUserId" 
              @change="(val) => handleToggle(row, val)"
              active-text="已订阅"
              inactive-text="未订阅"
              inline-prompt
            />
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'

const store = homeDataStore()
const currentUserId = store.user?.id
const loading = ref(false)
const tableData = ref([])

const fetchData = async () => {
  loading.value = true
  try {
    const res = await axios.get('/api/v1/notifications/subscribers')
    const rawData = res?.data || res
    tableData.value = Array.isArray(rawData) ? rawData : (rawData.data || [])
  } catch (error) {
    ElMessage.error('获取列表失败')
  } finally {
    loading.value = false
  }
}

const handleToggle = async (row, val) => {
  if (row.id !== currentUserId) {
      return 
  }
  row.loading = true
  try {
    await axios.post('/api/v1/notifications/subscribe', { is_enabled: val })
    ElMessage.success(val ? '已开启订阅' : '已取消订阅')
  } catch (error) {
    row.is_email_notify = !val // revert
    ElMessage.error('设置失败')
  } finally {
    row.loading = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.title {
  font-weight: 600;
}
</style>
