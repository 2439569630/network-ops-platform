<template>
  <el-card class="card nav-card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">个人中心</div>
      </div>
    </template>

    <div class="mini" v-loading="store.profileLoading">
      <div class="mini__top">
        <el-avatar :size="56" class="mini__avatar">
          <span>{{ store.initials }}</span>
        </el-avatar>
        <div class="mini__meta">
          <div class="mini__name">{{ store.displayName }}</div>
          <div class="mini__sub muted">账号：{{ store.form.username || '-' }}</div>
          <div class="mini__sub muted">邮箱：{{ store.form.email || '未绑定' }}</div>
        </div>
      </div>

      <div class="progress-wrap">
        <div class="progress-title">
          <span>资料完整度</span>
          <span class="muted">{{ store.completeness }}%</span>
        </div>
        <el-progress :percentage="store.completeness" :show-text="false" :color="customColors" />
      </div>
    </div>

    <el-divider />

    <el-menu class="nav" :default-active="activePage" @select="(key) => emit('select', key)">
      <el-menu-item index="overview">概览</el-menu-item>
      <el-menu-item index="profile">资料设置</el-menu-item>
      <el-menu-item index="email">邮箱设置</el-menu-item>
      <el-menu-item index="security">安全设置</el-menu-item>
    </el-menu>
  </el-card>
</template>

<script setup>
import { homeDataStore } from './data';

defineProps({
  activePage: {
    type: String,
    required: true
  }
});

const emit = defineEmits(['select']);
const store = homeDataStore();

const customColors = [
  { color: '#f56c6c', percentage: 25 },
  { color: '#e6a23c', percentage: 50 },
  { color: '#409eff', percentage: 75 },
  { color: '#67c23a', percentage: 100 }
];
</script>

<style scoped>
.card {
  border-radius: 14px;
  border: none;
  box-shadow: 0 10px 30px rgba(17, 24, 39, 0.06) !important;
}

.nav-card :deep(.el-card__body) {
  padding-top: 10px;
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

.mini {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.mini__top {
  display: flex;
  align-items: center;
  gap: 10px;
}

.mini__avatar {
  background: linear-gradient(135deg, rgba(64, 158, 255, 0.18), rgba(103, 194, 58, 0.16));
  border: 1px solid rgba(15, 23, 42, 0.06);
  color: #111827;
  font-weight: 800;
}

.mini__meta {
  min-width: 0;
}

.mini__name {
  font-weight: 800;
  color: #111827;
  font-size: 15px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.mini__sub {
  margin-top: 4px;
  font-size: 12px;
}

.progress-wrap {
  padding: 12px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.progress-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  margin-bottom: 8px;
}

.nav {
  border-right: none;
}
</style>
