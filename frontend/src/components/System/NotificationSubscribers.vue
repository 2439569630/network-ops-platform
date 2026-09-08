<template>
  <div class="notification-subscribers">
    <el-card shadow="never">
      <template #header>
        <div class="card-header">
          <span class="title">告警通知订阅</span>
          <el-button :icon="Refresh" circle @click="fetchData" />
        </div>
      </template>
      
      <div v-if="isMobile" class="mobile-list" v-loading="loading">
        <el-empty v-if="tableData.length === 0" description="暂无数据" />
        <div v-for="item in tableData" :key="item.id" class="sub-card">
          <div class="card-top">
            <div class="user-info">
              <div class="username">{{ item.nickname || item.username }}</div>
              <div class="email">{{ item.email || '无邮箱' }}</div>
            </div>
            <div class="action">
               <el-switch
                  v-model="item.is_email_notify"
                  :loading="item.loading"
                  :disabled="item.id !== currentUserId" 
                  @change="(val) => handleToggle(item, val)"
                  active-text="订阅"
                  inactive-text="关闭"
                  inline-prompt
                />
            </div>
          </div>
          <div v-if="item.username !== item.nickname" class="extra-info">
            用户名: {{ item.username }}
          </div>
        </div>
      </div>
      
      <el-table v-else :data="tableData" v-loading="loading" style="width: 100%">
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
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { Refresh } from '@element-plus/icons-vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'

const store = homeDataStore()
const currentUserId = store.user?.id
const loading = ref(false)
const tableData = ref([])
const isMobile = ref(false)

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768
}

onMounted(() => {
  checkMobile()
  window.addEventListener('resize', checkMobile)
  fetchData()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})

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
  checkMobile()
  window.addEventListener('resize', checkMobile)
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
