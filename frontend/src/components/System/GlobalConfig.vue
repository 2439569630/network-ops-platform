<template>
  <div class="global-config-page">
    <div class="page-header">
      <div class="header-title">
        <div class="title">系统配置</div>
        <div class="subtitle">自动热更新所操作配置</div>
      </div>
      <div class="header-meta">
        <el-tag v-if="dirtyItems.length" type="warning" effect="plain" size="small">
          {{ dirtyItems.length }} 项未保存
        </el-tag>
        <el-text v-else type="info" size="small">所有改动已保存</el-text>
      </div>
    </div>

    <el-card class="main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div class="card-header-left">
            <span class="card-title">{{ currentGroupLabel }}</span>
            <el-tag v-if="activeTabDirtyCount" size="small" type="warning" effect="plain">
              {{ activeTabDirtyCount }} 项未保存
            </el-tag>
          </div>
          <el-text type="info" size="small">回车或点击保存即可提交</el-text>
        </div>
      </template>

      <div v-loading="loading" class="content">
        <el-empty v-if="groupOrder.length === 0 && !loading" description="暂无配置数据" :image-size="160" />

        <el-tabs
          v-else
          v-model="activeTab"
          :tab-position="isMobile ? 'top' : 'left'"
          class="group-tabs"
        >
          <el-tab-pane
            v-for="group in groupOrder"
            :key="group"
            :label="getGroupLabel(group)"
            :name="group"
          >
            <div class="group-panel">
              <div class="group-header">
                <div class="group-name">{{ getGroupLabel(group) }}</div>
                <div class="group-desc">{{ groupDescriptions[group] || '' }}</div>
              </div>

              <el-row :gutter="16">
                <el-col
                  v-for="item in (visibleGroupedConfigs[group] || [])"
                  :key="item.key"
                  :xs="24"
                  :sm="24"
                  :md="12"
                  :lg="12"
                >
                  <div class="config-card" :class="{ dirty: isDirty(item) }">
                    <div class="meta">
                      <div class="label-row">
                        <div class="label">{{ item.description || item.key }}</div>
                        <div class="meta-actions">
                          <el-tag v-if="isDirty(item)" type="warning" size="small" effect="plain">未保存</el-tag>
                          <el-button link :icon="CopyDocument" @click="copyKey(item.key)">复制Key</el-button>
                        </div>
                      </div>
                      <div class="key">Key: {{ item.key }}</div>
                    </div>

                    <div class="control">
                      <el-switch
                        v-if="isBooleanKey(item.key)"
                        :model-value="toBoolean(item.value)"
                        active-text="启用"
                        inactive-text="关闭"
                        @update:model-value="(v) => setBooleanValue(item, v)"
                      />
                      <el-input
                        v-else
                        v-model="item.value"
                        :type="getInputType(item)"
                        :show-password="getInputType(item) === 'password'"
                        clearable
                        :placeholder="item.description || '请输入配置值'"
                        @keyup.enter="handleUpdate(item)"
                      />
                      <el-button
                        type="primary"
                        :disabled="!isDirty(item) || !!savingKeys[item.key]"
                        :loading="!!savingKeys[item.key]"
                        @click="handleUpdate(item)"
                      >
                        保存
                      </el-button>
                    </div>
                  </div>
                </el-col>
              </el-row>

              <el-empty
                v-if="(visibleGroupedConfigs[group] || []).length === 0 && !loading"
                description="没有可维护的配置项"
                :image-size="140"
                class="mt-16"
              />

              <div v-if="group === 'notification'" class="test-card">
                <el-divider content-position="left">连接测试</el-divider>
                <div class="test-row">
                  <el-input
                    v-model="testEmailTarget"
                    placeholder="输入测试邮箱地址"
                    style="max-width: 320px"
                    clearable
                  />
                  <el-button type="primary" @click="handleTestEmail">测试邮件发送</el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>
          <el-tab-pane
            v-if="hasPerm('sys:server:restart')"
            label="系统维护"
            name="maintenance"
          >
            <div class="group-panel">
              <div class="group-header">
                <div class="group-name">系统维护</div>
                <div class="group-desc">系统级操作与维护</div>
              </div>

              <el-row :gutter="16">
                <el-col :xs="24" :sm="24" :md="12" :lg="12">
                  <div class="config-card">
                    <div class="meta">
                      <div class="label-row">
                        <div class="label">重启服务</div>
                      </div>
                      <div class="key">重启所有后端子进程 (FastAPI, Monitor, Worker)</div>
                    </div>
                    <div class="control">
                      <el-button type="danger" @click="handleRestart">立即重启</el-button>
                    </div>
                  </div>
                </el-col>
              </el-row>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed } from 'vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { CopyDocument } from '@element-plus/icons-vue';
import { homeDataStore } from '@/components/home/home/data';

const store = homeDataStore();
const isSuper = computed(() => (typeof store.isSuperAdmin === 'function' ? store.isSuperAdmin() : Boolean(store.isSuper)));
const permissions = computed(() => (Array.isArray(store.permissions) ? store.permissions : []));

const hasPerm = (perm) => {
    if (isSuper.value) return true;
    return permissions.value.includes(perm);
};

const loading = ref(false);
const configs = ref([]);
const activeTab = ref('');
const testEmailTarget = ref('');
const savingKeys = ref({});
const originalValues = ref({});
const isMobile = ref(false);

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768;
};

onMounted(() => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
  fetchConfigs();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile);
});

const ALLOWED_GROUPS = new Set(['notification', 'repair', 'security']);

const groupDescriptions = {
  notification: '邮件通知渠道配置（不涉及设备监控参数）',
  repair: '图片服务相关配置',
  security: '系统安全相关配置'
};

const getGroupLabel = (group) => {
  const map = {
    notification: '消息渠道配置',
    repair: '图片服务配置',
    security: '系统安全',
    maintenance: '系统维护'
  };
  return map[group] || group;
};

const isDirty = (item) => {
  const original = originalValues.value[item.key];
  return original !== undefined && String(item.value ?? '') !== String(original ?? '');
};

const dirtyItems = computed(() => configs.value.filter(isDirty));

const groupedConfigs = computed(() => {
  const groups = {};
  configs.value.forEach(item => {
    const groupName = item.group_name || 'other';
    if (!groups[groupName]) groups[groupName] = [];
    groups[groupName].push(item);
  });
  Object.keys(groups).forEach(group => {
    groups[group] = [...groups[group]].sort((a, b) => String(a.key).localeCompare(String(b.key)));
  });
  return groups;
});

const groupOrder = computed(() => {
  const keys = Object.keys(groupedConfigs.value);
  const priority = ['notification', 'repair'];
  return [
    ...priority.filter(k => keys.includes(k)),
    ...keys.filter(k => !priority.includes(k)).sort((a, b) => String(a).localeCompare(String(b)))
  ];
});

const currentGroupLabel = computed(() => getGroupLabel(activeTab.value || (groupOrder.value[0] || '')));

const activeTabDirtyCount = computed(() => {
  const tab = activeTab.value;
  if (!tab) return 0;
  const list = groupedConfigs.value[tab] || [];
  return list.filter(isDirty).length;
});

const visibleGroupedConfigs = computed(() => groupedConfigs.value);

const getInputType = (item) => {
  const key = String(item.key || '').toLowerCase();
  if (isBooleanKey(key)) return 'text';
  if (key.includes('password') || key.includes('passwd') || key.includes('secret')) return 'password';
  if (key.includes('token') || key.includes('api_key') || key.includes('apikey')) return 'password';
  if (key.includes('port') || key.includes('timeout') || key.includes('interval') || key.includes('ttl')) return 'number';
  return 'text';
};

const isBooleanKey = (key) => {
  const k = String(key || '').trim().toLowerCase();
  return k === 'email_enabled' || k.endsWith('_enabled');
};

const toBoolean = (value) => {
  const s = String(value ?? '').trim().toLowerCase();
  if (s === '1' || s === 'true' || s === 'yes' || s === 'on') return true;
  return false;
};

const setBooleanValue = (item, enabled) => {
  if (!item) return;
  item.value = enabled ? 'true' : 'false';
};

const fetchConfigs = async () => {
  loading.value = true;
  try {
    const res = await axios.get('/api/v1/system/config/list');
    if (res.data.code === 200) {
      const raw = Array.isArray(res.data.data) ? res.data.data : [];
      const filtered = raw.filter(i => ALLOWED_GROUPS.has(String(i?.group_name || '')));
      configs.value = filtered;

      const nextOriginal = {};
      filtered.forEach(i => {
        if (i?.key !== undefined) nextOriginal[i.key] = i.value;
      });
      originalValues.value = nextOriginal;

      if (!activeTab.value || !Object.keys(groupedConfigs.value).includes(activeTab.value)) {
        activeTab.value = groupOrder.value[0] || '';
      }
    } else {
      ElMessage.error(res.data.message || '获取配置失败');
    }
  } catch (error) {
    ElMessage.error('获取配置失败: ' + (error.response?.data?.detail?.message || error.message));
  } finally {
    loading.value = false;
  }
};

const handleUpdate = async (item) => {
  if (!item?.key) return;
  if (!isDirty(item)) {
    ElMessage.info('当前项未发生变化');
    return;
  }
  savingKeys.value = { ...savingKeys.value, [item.key]: true };
  try {
    const res = await axios.post('/api/v1/system/config/update', {
      key: item.key,
      value: item.value
    });

    if (res.data.code === 200) {
      ElMessage.success('配置更新成功');
      originalValues.value = { ...originalValues.value, [item.key]: item.value };
    } else {
      ElMessage.error(res.data.message || '更新失败');
    }
  } catch (error) {
    ElMessage.error('更新失败: ' + (error.response?.data?.detail?.message || error.message));
  } finally {
    const { [item.key]: _, ...rest } = savingKeys.value;
    savingKeys.value = rest;
  }
};

const copyKey = async (key) => {
  try {
    await navigator.clipboard.writeText(String(key || ''));
    ElMessage.success('已复制');
  } catch {
    ElMessage.error('复制失败');
  }
};

const handleTestEmail = async () => {
  const target = String(testEmailTarget.value || '').trim();
  if (!target) {
    ElMessage.warning('请输入测试邮箱地址');
    return;
  }
  try {
    const res = await axios.post('/api/v1/notifications/test', {
      channel: 'email',
      target
    });
    if (res.data.code === 200) ElMessage.success(res.data.message || '发送成功');
    else ElMessage.error(res.data.message || '发送失败');
  } catch (error) {
    ElMessage.error('发送失败: ' + (error.response?.data?.detail?.message || error.message));
  }
};

const handleRestart = async () => {
  try {
    await ElMessageBox.confirm('确定要重启所有后端子进程吗？此操作可能导致短暂的服务中断。', '系统重启', {
      confirmButtonText: '确定重启',
      cancelButtonText: '取消',
      type: 'warning'
    });
    
    const res = await axios.post('/api/v1/system/restart');
    if (res.data.code === 200) {
      ElMessage.success(res.data.message || '系统重启指令已发送');
    } else {
      ElMessage.error(res.data.message || '重启失败');
    }
  } catch (error) {
    if (error === 'cancel') return;
    ElMessage.error('重启失败: ' + (error.response?.data?.detail?.message || error.message));
  }
};

</script>

<style scoped>
.global-config-page {
  padding: 16px;
}

@media (max-width: 768px) {
  .global-config-page {
    padding: 12px;
  }
  
  .page-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 12px;
  }
  
  .header-meta {
    width: 100%;
    display: flex;
    justify-content: flex-end;
  }

  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .card-header-left {
    width: 100%;
    justify-content: space-between;
  }
  
  .control {
    flex-direction: column;
  }
  
  .test-row {
    flex-direction: column;
    align-items: stretch;
  }
  
  .test-row .el-input {
    max-width: 100% !important;
  }
  
  .test-row .el-button {
    width: 100%;
  }
}

.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 12px;
}

.header-title .title {
  font-size: 18px;
  font-weight: 600;
  line-height: 1.2;
}

.header-title .subtitle {
  margin-top: 6px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.main-card :deep(.el-card__header) {
  padding: 12px 16px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.card-title {
  font-weight: 600;
}

.content {
  min-height: 240px;
}

.group-header {
  margin-bottom: 12px;
}

.group-name {
  font-weight: 600;
}

.group-desc {
  margin-top: 4px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.config-card {
  border: 1px solid var(--el-border-color-light);
  border-radius: 8px;
  padding: 12px;
  margin-bottom: 12px;
  background: var(--el-bg-color);
}

.config-card.dirty {
  border-color: var(--el-color-warning);
}

.label-row {
  display: flex;
  justify-content: space-between;
  gap: 8px;
}

.label {
  font-weight: 500;
}

.key {
  margin-top: 6px;
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.control {
  margin-top: 10px;
  display: flex;
  gap: 10px;
}

.test-card {
  margin-top: 8px;
}

.test-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
</style>
