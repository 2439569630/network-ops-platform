<template>
  <div>
    <el-card class="card" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="card-title">最近工单</div>
        </div>
      </template>

      <el-skeleton v-if="store.ordersLoading" :rows="5" animated />
      <div v-else>
        <el-empty v-if="store.recentOrders.length === 0" description="暂无工单" />
        <el-table v-else :data="store.recentOrders" size="small" style="width: 100%">
          <el-table-column prop="id" label="ID" width="80" />
          <el-table-column prop="title" label="标题" min-width="220" show-overflow-tooltip />
          <el-table-column label="状态" width="120">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" effect="light">{{ statusText(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="创建时间" width="180">
            <template #default="{ row }">
              <span class="muted">{{ formatTime(row.created_at) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-card>

    <el-card class="card mt" shadow="hover">
      <template #header>
        <div class="card-header">
          <div class="card-title">通知动态</div>
        </div>
      </template>

      <el-skeleton v-if="store.historyLoading" :rows="4" animated />
      <div v-else class="notify-list">
        <el-empty v-if="store.notificationHistory.length === 0" description="暂无通知" />
        <div v-else class="notify-item" v-for="n in store.notificationHistory" :key="n.id || n.created_at">
          <div class="notify-item__time">{{ formatTime(n.created_at) }}</div>
          <div class="notify-item__main">
            <div class="notify-item__title">{{ n.title || '系统通知' }}</div>
            <div class="notify-item__content">{{ n.content || '-' }}</div>
          </div>
        </div>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { homeDataStore } from './data';

const store = homeDataStore();

const formatTime = (value) => {
  if (!value) return '-';
  const s = String(value);
  if (s.includes('T')) return s.replace('T', ' ').slice(0, 19);
  return s.slice(0, 19);
};

const statusText = (s) => {
  const v = String(s || '');
  if (v === 'pending') return '待处理';
  if (v === 'processing') return '处理中';
  if (v === 'need_info') return '需补充';
  if (v === 'completed') return '已完成';
  if (v === 'closed') return '已关闭';
  if (v === 'cancelled') return '已取消';
  return v || '-';
};

const statusTagType = (s) => {
  const v = String(s || '');
  if (v === 'pending') return 'warning';
  if (v === 'processing') return 'primary';
  if (v === 'need_info') return 'danger';
  if (v === 'completed' || v === 'closed') return 'success';
  if (v === 'cancelled') return 'info';
  return '';
};
</script>

<style scoped>
.card {
  border-radius: 14px;
  border: none;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.06) !important;
}

.mt {
  margin-top: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.card-title {
  font-weight: 700;
  color: #111827;
}

.muted {
  color: #6b7280;
}

.notify-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.notify-item {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 12px;
  padding: 12px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.notify-item__time {
  color: #6b7280;
  font-size: 12px;
}

.notify-item__title {
  font-weight: 700;
  color: #111827;
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.notify-item__content {
  margin-top: 4px;
  color: #4b5563;
  font-size: 13px;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

@media (max-width: 720px) {
  .notify-item {
    grid-template-columns: 1fr;
  }
}
</style>

