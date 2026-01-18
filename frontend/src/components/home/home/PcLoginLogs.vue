<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">登录记录</div>
        <el-button link type="primary" @click="fetchLogs">刷新</el-button>
      </div>
    </template>

    <el-table :data="logs" v-loading="loading" style="width: 100%">
      <el-table-column prop="created_at" label="登录时间" width="180" />
      <el-table-column prop="ip" label="IP 地址" width="150" />
      <el-table-column prop="device" label="设备信息" />
    </el-table>

    <div class="pagination">
      <el-pagination
        v-model:current-page="page"
        v-model:page-size="pageSize"
        :total="total"
        layout="prev, pager, next"
        @current-change="fetchLogs"
      />
    </div>
  </el-card>
</template>

<script setup>
import { onMounted, ref } from 'vue';
import axios from '@/axios/axios';

const logs = ref([]);
const loading = ref(false);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);

const fetchLogs = async () => {
  loading.value = true;
  try {
    const res = await axios.get('/api/v1/auth/users/me/login-logs', {
      params: { page: page.value, page_size: pageSize.value }
    });
    if (res.data.code === 200) {
      logs.value = res.data.data.items;
      total.value = res.data.data.total;
    }
  } catch (e) {
    console.error(e);
  } finally {
    loading.value = false;
  }
};

onMounted(() => {
  fetchLogs();
});
</script>

<style scoped>
.card {
  border-radius: 14px;
  border: none;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.06) !important;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-weight: 700;
  color: #111827;
}

.pagination {
  margin-top: 20px;
  display: flex;
  justify-content: flex-end;
}
</style>
