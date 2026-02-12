<template>
  <div class="audit-page">
    <div class="page-header">
      <div class="header-main">
        <div class="header-title">
          <div class="title">系统操作审计</div>
          <div class="subtitle">查看用户管理等后台操作审计记录</div>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="main-card">
      <div class="filter-bar">
        <el-input
          v-model="query.actor_username"
          placeholder="操作者用户名"
          clearable
          class="filter-item"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="query.action"
          placeholder="动作（如 user.delete）"
          clearable
          class="filter-item"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-input
          v-model="query.target_user_id"
          placeholder="目标用户ID"
          clearable
          class="filter-item"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-date-picker
          v-model="query.timeRange"
          type="datetimerange"
          range-separator="至"
          start-placeholder="开始时间"
          end-placeholder="结束时间"
          value-format="YYYY-MM-DDTHH:mm:ss"
          class="filter-item date-range"
        />
        <div class="filter-actions">
          <el-button type="primary" @click="handleSearch">查询</el-button>
          <el-button @click="resetFilter">重置</el-button>
        </div>
      </div>

      <div v-if="isMobile" class="mobile-list" v-loading="loading">
        <el-empty v-if="tableData.length === 0" description="暂无数据" />
        <div v-for="item in tableData" :key="item.id" class="audit-card">
          <div class="card-header">
            <span class="action-title">{{ item.action_label || item.action }}</span>
            <span class="time">{{ formatTime(item.created_at) }}</span>
          </div>
          <div class="card-body">
            <div class="info-row">
              <span class="label">操作者:</span>
              <span class="value">{{ item.actor_username }}</span>
            </div>
            <div class="info-row">
              <span class="label">动作代码:</span>
              <span class="value code">{{ item.action }}</span>
            </div>
            <div class="info-row">
              <span class="label">目标用户ID:</span>
              <span class="value">{{ item.target_user_id }}</span>
            </div>
            <div class="info-row">
              <span class="label">IP地址:</span>
              <span class="value">{{ item.request_ip }}</span>
            </div>
          </div>
        </div>
      </div>

      <el-table v-else :data="tableData" border stripe style="width: 100%" v-loading="loading">
        <el-table-column prop="created_at" label="时间" width="190">
          <template #default="{ row }">
            {{ formatTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column prop="actor_username" label="操作者" width="140" />
        <el-table-column prop="action" label="动作" min-width="220">
          <template #default="{ row }">
            <div class="action-cell">
              <div class="action-label">{{ row.action_label || row.action }}</div>
              <div class="action-code">{{ row.action }}</div>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="target_user_id" label="目标用户ID" width="120" />
        <el-table-column prop="request_ip" label="IP" width="140" />
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[20, 50, 100, 200]"
          :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          :small="isMobile"
          background
          @current-change="fetchLogs"
          @size-change="fetchLogs"
        />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';

const loading = ref(false);
const tableData = ref([]);
const total = ref(0);
const isMobile = ref(false);

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768;
};

onMounted(() => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
  fetchLogs();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile);
});

const query = reactive({
  page: 1,
  page_size: 50,
  actor_username: '',
  action: '',
  target_user_id: '',
  timeRange: null
});

const formatTime = (v) => {
  if (!v) return '-';
  try {
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return String(v);
    return d.toLocaleString();
  } catch {
    return String(v);
  }
};

const fetchLogs = async () => {
  loading.value = true;
  try {
    const params = {
      page: query.page,
      page_size: query.page_size,
      actor_username: query.actor_username || undefined,
      action: query.action || undefined
    };
    if (query.target_user_id) {
      const n = Number(query.target_user_id);
      if (!Number.isNaN(n)) params.target_user_id = n;
    }
    if (Array.isArray(query.timeRange) && query.timeRange.length === 2) {
      params.start_at = query.timeRange[0];
      params.end_at = query.timeRange[1];
    }
    const res = await axios.get('/api/v1/system/audit/user-admin', { params });
    if (res.data?.code === 200) {
      tableData.value = res.data.data || [];
      total.value = res.data.meta?.total || 0;
      return;
    }
    ElMessage.error(res.data?.message || '获取审计日志失败');
  } catch (e) {
    ElMessage.error('获取审计日志失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = async () => {
  query.page = 1;
  await fetchLogs();
};

const resetFilter = async () => {
  query.page = 1;
  query.page_size = 50;
  query.actor_username = '';
  query.action = '';
  query.target_user_id = '';
  query.timeRange = null;
  await fetchLogs();
};

onMounted(() => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
  fetchLogs();
});
</script>

<style scoped>
.audit-page {
  padding: 16px;
}
.page-header {
  margin-bottom: 12px;
}
.header-title .title {
  font-size: 18px;
  font-weight: 600;
}
.header-title .subtitle {
  font-size: 12px;
  color: #6b7280;
  margin-top: 2px;
}
.filter-bar {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.filter-item {
  max-width: 200px;
}
.date-range {
  max-width: 360px;
}
.filter-actions {
  display: flex;
  gap: 10px;
}

.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.action-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}
.action-label {
  font-weight: 600;
}
.action-code {
  margin-top: 2px;
  font-size: 12px;
  color: #6b7280;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .audit-page {
    padding: 12px;
  }
  
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  
  .filter-item, .date-range {
    max-width: 100% !important;
    width: 100%;
  }
  
  .filter-actions {
    display: grid;
    grid-template-columns: 1fr 1fr;
    width: 100%;
  }
  
  .filter-actions .el-button {
    width: 100%;
  }
  
  .pagination {
    justify-content: center;
  }
  
  .mobile-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  
  .audit-card {
    border: 1px solid var(--el-border-color-light);
    border-radius: 8px;
    padding: 12px;
    background: #fff;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
    border-bottom: 1px solid var(--el-border-color-lighter);
    padding-bottom: 8px;
  }
  
  .action-title {
    font-weight: 600;
    color: var(--el-color-primary);
  }
  
  .time {
    font-size: 12px;
    color: #909399;
  }
  
  .info-row {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    margin-bottom: 4px;
  }
  
  .label {
    color: #606266;
  }
  
  .value {
    color: #303133;
    font-weight: 500;
  }
  
  .value.code {
    font-family: monospace;
    background: #f4f4f5;
    padding: 0 4px;
    border-radius: 4px;
  }
}
</style>
