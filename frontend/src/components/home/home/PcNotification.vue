<template>
  <el-card class="card" shadow="hover">
    <template #header>
      <div class="card-header">
        <div class="card-title">通知策略</div>
      </div>
    </template>

    <div class="hint">
      <div class="hint__title">统一配置</div>
      <div class="hint__desc">通知策略由管理员统一配置，普通用户不可修改。</div>
    </div>

    <el-form label-width="150px" label-position="left" v-loading="store.notifyLoading" class="form">
      <el-form-item label="启用邮件通知">
        <el-switch :model-value="!!store.notifyConfig.enable_email" disabled />
      </el-form-item>
      <el-form-item label="使用全局邮箱配置">
        <el-switch :model-value="!!store.notifyConfig.use_global_email" disabled />
      </el-form-item>
      <el-form-item label="启用 PushPlus">
        <el-switch :model-value="!!store.notifyConfig.enable_pushplus" disabled />
      </el-form-item>
      <el-form-item label="启用 HTTP 回调">
        <el-switch :model-value="!!store.notifyConfig.enable_http" disabled />
      </el-form-item>
    </el-form>
  </el-card>
</template>

<script setup>
import { homeDataStore } from './data';

const store = homeDataStore();
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
  gap: 12px;
}

.card-title {
  font-weight: 700;
  color: #111827;
}

.form {
  max-width: 720px;
}

.hint {
  padding: 12px 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid rgba(15, 23, 42, 0.06);
  margin-bottom: 14px;
}

.hint__title {
  font-weight: 800;
  color: #111827;
}

.hint__desc {
  margin-top: 6px;
  color: #6b7280;
  font-size: 13px;
}
</style>

