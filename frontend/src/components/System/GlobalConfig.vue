<template>
  <div class="global-config-page">
    <div class="page-header">
      <div class="header-main">
        <div class="header-title">
          <div class="title">全局配置</div>
          <div class="subtitle">统一管理系统监控、安全、基础参数与消息渠道</div>
        </div>

        <div class="header-actions">
          <el-input
            v-model="searchText"
            clearable
            class="search"
            placeholder="搜索 Key / 描述"
            :prefix-icon="Search"
          />

          <div class="action-group">
            <el-switch v-model="onlyChanged" inline-prompt active-text="仅改动" inactive-text="全部" />
            <el-button :icon="Refresh" @click="fetchConfigs" :loading="loading">刷新</el-button>
            <el-button
              type="primary"
              :icon="Check"
              :disabled="dirtyItems.length === 0 || loading"
              :loading="savingAll"
              @click="handleSaveAll"
            >
              保存全部
            </el-button>
          </div>
        </div>
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
          :tab-position="tabPosition"
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
                      <el-input
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
                description="没有匹配的配置项"
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
                  <el-button type="primary" @click="handleTestGlobalEmail">测试邮件发送</el-button>
                  <el-button @click="handleTestGlobalPushPlus">测试 PushPlus</el-button>
                </div>
              </div>
            </div>
          </el-tab-pane>
        </el-tabs>
      </div>
    </el-card>
</div>
</template>

<script setup>
import { ref, onMounted, computed, onBeforeUnmount } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import { Check, CopyDocument, Refresh, Search } from '@element-plus/icons-vue';

const loading = ref(false);
const configs = ref([]);
const activeTab = ref('');
const testEmailTarget = ref('');
const searchText = ref('');
const onlyChanged = ref(false);
const savingKeys = ref({});
const savingAll = ref(false);
const originalValues = ref({});
const tabPosition = ref('left'); // 动态控制 Tabs 位置

const groupedConfigs = computed(() => {
  const groups = {};
  configs.value.forEach(item => {
    const groupName = item.group_name || 'other';
    if (!groups[groupName]) {
      groups[groupName] = [];
    }
    groups[groupName].push(item);
  });
  Object.keys(groups).forEach(group => {
    groups[group] = [...groups[group]].sort((a, b) => String(a.key).localeCompare(String(b.key)));
  });
  return groups;
});

const groupDescriptions = {
  monitor: '采集频率、阈值与健康检查相关参数',
  security: '鉴权、安全策略与敏感配置项',
  system: '系统通用配置与运行参数',
  notification: '消息推送渠道（邮件、PushPlus 等）'
};

const getGroupLabel = (group) => {
  const map = {
    'monitor': '监控配置',
    'security': '安全配置',
    'system': '系统配置',
    'notification': '消息渠道配置'
  };
  return map[group] || group;
};

const groupOrder = computed(() => {
  const keys = Object.keys(groupedConfigs.value);
  const priority = ['monitor', 'system', 'security', 'notification'];
  const sorted = [
    ...priority.filter(k => keys.includes(k)),
    ...keys.filter(k => !priority.includes(k)).sort((a, b) => String(a).localeCompare(String(b)))
  ];
  return sorted;
});

const currentGroupLabel = computed(() => getGroupLabel(activeTab.value || (groupOrder.value[0] || '')));

const isDirty = (item) => {
  const original = originalValues.value[item.key];
  return original !== undefined && String(item.value ?? '') !== String(original ?? '');
};

const dirtyItems = computed(() => configs.value.filter(isDirty));

const activeTabDirtyCount = computed(() => {
  const tab = activeTab.value;
  if (!tab) return 0;
  const list = groupedConfigs.value[tab] || [];
  return list.filter(isDirty).length;
});

const visibleGroupedConfigs = computed(() => {
  const needle = searchText.value.trim().toLowerCase();
  const result = {};

  Object.entries(groupedConfigs.value).forEach(([group, items]) => {
    let list = items;
    if (needle) {
      list = list.filter(i => {
        const hay1 = String(i.key || '').toLowerCase();
        const hay2 = String(i.description || '').toLowerCase();
        return hay1.includes(needle) || hay2.includes(needle);
      });
    }
    if (onlyChanged.value) {
      list = list.filter(isDirty);
    }
    result[group] = list;
  });

  return result;
});

const getInputType = (item) => {
  const key = String(item.key || '').toLowerCase();
  if (key.includes('password') || key.includes('passwd') || key.includes('secret')) return 'password';
  if (key.includes('token') || key.includes('api_key') || key.includes('apikey')) return 'password';
  if (key.includes('port') || key.includes('timeout') || key.includes('interval') || key.includes('ttl')) return 'number';
  return 'text';
};

const fetchConfigs = async () => {
  loading.value = true;
  try {
    const res = await axios.get('/api/v1/system/config/list');
    if (res.data.code === 200) {
      configs.value = res.data.data;
      const nextOriginal = {};
      (res.data.data || []).forEach(i => {
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

const handleSaveAll = async () => {
  if (dirtyItems.value.length === 0) return;
  savingAll.value = true;
  let success = 0;
  let fail = 0;
  for (const item of dirtyItems.value) {
    try {
      const res = await axios.post('/api/v1/system/config/update', {
        key: item.key,
        value: item.value
      });
      if (res.data.code === 200) {
        success += 1;
        originalValues.value = { ...originalValues.value, [item.key]: item.value };
      } else {
        fail += 1;
      }
    } catch (e) {
      fail += 1;
    }
  }
  savingAll.value = false;
  if (fail === 0) {
    ElMessage.success(`保存完成（${success} 项）`);
  } else if (success === 0) {
    ElMessage.error(`保存失败（${fail} 项）`);
  } else {
    ElMessage.warning(`部分成功：成功 ${success} 项，失败 ${fail} 项`);
  }
};

const copyKey = async (key) => {
  try {
    await navigator.clipboard.writeText(String(key));
    ElMessage.success('已复制 Key');
  } catch (e) {
    ElMessage.error('复制失败');
  }
};

const handleTestGlobalEmail = async () => {
    if (!testEmailTarget.value) {
        ElMessage.warning('请输入测试接收邮箱');
        return;
    }
    const hostItem = configs.value.find(i => i.key === 'email_host');
    const portItem = configs.value.find(i => i.key === 'email_port');
    const usernameItem = configs.value.find(i => i.key === 'email_username');
    const passwordItem = configs.value.find(i => i.key === 'email_password');
    const nicknameItem = configs.value.find(i => i.key === 'email_nickname');
    if (!hostItem?.value || !portItem?.value || !usernameItem?.value || !passwordItem?.value) {
        ElMessage.warning('请先完善全局邮箱配置');
        return;
    }
    const payload = {
        channel: 'email',
        config: {
            email_config: {
                host: hostItem.value,
                port: portItem.value,
                username: usernameItem.value,
                password: passwordItem.value,
            },
            email_nickname: nicknameItem?.value || '',
        },
        target: testEmailTarget.value
    };
    await sendTestRequest(payload);
};

const handleTestGlobalPushPlus = async () => {
    const tokenItem = configs.value.find(i => i.key === 'pushplus_token');
    if (!tokenItem || !tokenItem.value) {
        ElMessage.warning('请先填写 PushPlus Token');
        return;
    }
    
    const payload = {
        channel: 'pushplus',
        config: { pushplus_token: tokenItem.value },
        target: null
    };
    await sendTestRequest(payload);
};

const sendTestRequest = async (payload) => {
    try {
        const res = await axios.post('/api/v1/notifications/test', payload);
        if (res.data.code === 200) {
            ElMessage.success('测试发送成功');
        } else {
            ElMessage.error(res.data.message || '测试失败');
        }
    } catch (error) {
        ElMessage.error('测试请求失败: ' + (error.response?.data?.detail?.message || error.message));
    }
};

// Responsive logic
const handleResize = () => {
    if (window.innerWidth <= 768) {
        tabPosition.value = 'top';
    } else {
        tabPosition.value = 'left';
    }
};

onMounted(() => {
  fetchConfigs();
  handleResize();
  window.addEventListener('resize', handleResize);
});

onBeforeUnmount(() => {
    window.removeEventListener('resize', handleResize);
});
</script>

<style scoped>
.global-config-page {
  padding: 20px;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-header {
  padding: 18px 18px 14px;
  border-radius: 14px;
  background: radial-gradient(1200px 280px at 20% 0%, rgba(64, 158, 255, 0.18), transparent 60%),
              radial-gradient(900px 260px at 80% 20%, rgba(103, 194, 58, 0.14), transparent 55%),
              linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(255, 255, 255, 0.86));
  border: 1px solid rgba(230, 230, 230, 0.8);
  backdrop-filter: blur(10px);
}
.header-main {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}
.header-title .title {
  font-size: 18px;
  font-weight: 700;
  color: #1f2d3d;
}
.header-title .subtitle {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.search {
  width: 320px;
}
.action-group {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.header-meta {
  margin-top: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}

.main-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  border-radius: 14px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.card-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.card-title {
  font-weight: 600;
  color: #1f2d3d;
}
.content {
  min-height: 240px;
}
.group-tabs :deep(.el-tabs__header) {
  width: 170px;
}
.group-tabs :deep(.el-tabs__nav-wrap) {
  padding: 6px 0;
}
.group-tabs :deep(.el-tabs__item) {
  height: 44px;
  line-height: 44px;
  margin: 4px 10px;
  border-radius: 10px;
  color: #303133;
}
.group-tabs :deep(.el-tabs__item.is-active) {
  background: rgba(64, 158, 255, 0.12);
}
.group-panel {
  padding: 6px 6px 4px;
}
.group-header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 14px;
}
.group-name {
  font-size: 14px;
  font-weight: 700;
  color: #1f2d3d;
}
.group-desc {
  font-size: 12px;
  color: #909399;
}
.config-card {
  border: 1px solid rgba(235, 238, 245, 1);
  border-radius: 12px;
  padding: 14px 14px 12px;
  background: linear-gradient(180deg, #ffffff, rgba(255, 255, 255, 0.96));
  box-shadow: 0 6px 18px rgba(31, 45, 61, 0.06);
  transition: transform 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
  min-height: 128px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.config-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 10px 26px rgba(31, 45, 61, 0.1);
}
.config-card.dirty {
  border-color: rgba(230, 162, 60, 0.55);
  box-shadow: 0 10px 28px rgba(230, 162, 60, 0.14);
}
.meta .label-row {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: flex-start;
}
.meta .label {
  font-weight: 600;
  color: #1f2d3d;
  line-height: 20px;
  word-break: break-word;
}
.meta-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}
.meta .key {
  margin-top: 6px;
  font-size: 12px;
  color: #909399;
}
.control {
  display: flex;
  gap: 10px;
  align-items: center;
}
.control :deep(.el-input) {
  flex: 1;
}
.test-card {
  margin-top: 16px;
  padding: 12px 14px 14px;
  border-radius: 12px;
  border: 1px dashed rgba(200, 200, 200, 0.9);
  background: rgba(248, 249, 250, 0.7);
}
.test-row {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}
.mt-16 {
  margin-top: 16px;
}

@media (max-width: 768px) {
  .global-config-page {
    padding: 0;
    gap: 0;
    height: auto;
    min-height: 100vh;
    background-color: #f5f7fa;
  }

  .page-header {
    border-radius: 0 0 20px 20px;
    margin-bottom: 16px;
    padding: 20px 16px;
    border: none;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
  }

  .header-main {
    flex-direction: column;
    align-items: stretch;
    gap: 16px;
  }

  .header-title .title {
    font-size: 22px;
  }

  .header-actions {
    justify-content: flex-start;
    flex-direction: column;
    align-items: stretch;
  }

  .search {
    width: 100%;
  }

  .action-group {
    justify-content: space-between;
    width: 100%;
  }

  .main-card {
    border-radius: 20px 20px 0 0;
    border: none;
    flex: 1;
    margin: 0;
  }

  /* Card Header Mobile */
  .card-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 8px;
  }
  
  .card-header .el-text {
      display: none;
  }

  /* Tabs Mobile */
  .group-tabs {
      height: auto;
  }
  
  .group-tabs :deep(.el-tabs__header) {
    width: 100%;
    margin-right: 0;
    margin-bottom: 16px;
    float: none;
    position: sticky;
    top: 0;
    z-index: 10;
    background-color: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(10px);
    padding: 10px 0;
    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
    transition: all 0.3s ease;
  }

  .group-panel {
      padding: 0 4px;
  }

  .group-tabs :deep(.el-tabs__nav-wrap) {
      padding: 0 16px;
      mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
      -webkit-mask-image: linear-gradient(90deg, transparent, #000 4%, #000 96%, transparent);
  }
  
  .group-tabs :deep(.el-tabs__nav-scroll) {
      overflow-x: auto;
      white-space: nowrap;
      -webkit-overflow-scrolling: touch;
      padding-bottom: 0;
      scrollbar-width: none; /* Firefox */
  }
  
  .group-tabs :deep(.el-tabs__nav-scroll)::-webkit-scrollbar {
      display: none; /* Chrome/Safari */
  }
  
  .group-tabs :deep(.el-tabs__nav) {
      float: none;
      display: flex;
      gap: 8px;
  }

  .group-tabs :deep(.el-tabs__item) {
    height: 32px;
    margin: 0;
    padding: 0 16px;
    border-radius: 16px;
    background-color: #f5f7fa;
    color: #606266;
    font-size: 13px;
    flex-shrink: 0;
    border: none;
    transition: all 0.3s;
    display: flex;
    align-items: center;
    justify-content: center;
  }
  
  .group-tabs :deep(.el-tabs__item.is-active) {
      background-color: var(--el-color-primary);
      color: #fff;
      font-weight: 500;
      box-shadow: 0 2px 6px rgba(64, 158, 255, 0.3);
  }

  
  .group-tabs :deep(.el-tabs__active-bar) {
      display: none;
  }
  
  .group-tabs :deep(.el-tabs__content) {
      padding: 0 4px 40px 4px; /* Bottom padding for mobile */
  }

  /* Config Card Mobile */
  .config-card {
      padding: 16px;
      margin-bottom: 12px;
      min-height: auto;
  }
  
  .meta .label-row {
      flex-direction: column;
      gap: 4px;
  }
  
  .meta-actions {
      width: 100%;
      justify-content: space-between;
      margin-top: 4px;
  }
  
  .control {
      flex-direction: column;
      align-items: stretch;
      margin-top: 12px;
  }
  
  .control .el-button {
      width: 100%;
  }
  
  .test-row {
      flex-direction: column;
      align-items: stretch;
  }
  .test-row .el-input {
      max-width: 100% !important;
  }
}
</style>
