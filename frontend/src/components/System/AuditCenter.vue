<template>
  <div class="audit-page">
    <div class="page-header">
      <div class="header-main">
        <div class="header-title">
          <div class="title">系统日志与审计中心</div>
          <div class="subtitle">统一入口查看系统操作、登录、设备位置与WebSSH审计记录</div>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="main-card">
      <el-tabs v-model="activeTab" @tab-change="handleTabChange">
        <el-tab-pane label="系统操作审计" name="user-admin">
          <div class="filter-bar">
            <el-input
              v-model="userAdminQuery.actor_username"
              placeholder="操作者用户名"
              clearable
              class="filter-item"
              @keyup.enter="handleUserAdminSearch"
              @clear="handleUserAdminSearch"
            />
            <el-input
              v-model="userAdminQuery.action"
              placeholder="动作（如 user.delete）"
              clearable
              class="filter-item"
              @keyup.enter="handleUserAdminSearch"
              @clear="handleUserAdminSearch"
            />
            <el-select
              v-model="userAdminQuery.target_type"
              placeholder="目标类型"
              clearable
              class="filter-item"
              @change="handleUserAdminSearch"
            >
              <el-option label="用户(user)" value="user" />
              <el-option label="角色(role)" value="role" />
              <el-option label="权限(permission)" value="permission" />
              <el-option label="禁用权限列表(permission.disabled_list)" value="permission.disabled_list" />
              <el-option label="系统(system)" value="system" />
            </el-select>
            <el-input
              v-model="userAdminQuery.target_user_id"
              placeholder="目标用户ID"
              clearable
              class="filter-item"
              @keyup.enter="handleUserAdminSearch"
              @clear="handleUserAdminSearch"
            />
            <el-date-picker
              v-model="userAdminQuery.timeRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              value-format="YYYY-MM-DDTHH:mm:ss"
              class="filter-item date-range"
            />
            <div class="filter-actions">
              <el-button type="primary" @click="handleUserAdminSearch">查询</el-button>
              <el-button @click="resetUserAdminFilter">重置</el-button>
            </div>
          </div>

          <el-table :data="userAdminTableData" border stripe style="width: 100%" v-loading="userAdminLoading">
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
            <el-table-column label="目标" min-width="220">
              <template #default="{ row }">
                <div class="target-cell">
                  <div class="target-main">{{ formatTarget(row) }}</div>
                  <div class="target-sub" v-if="row.target_user_id">target_user_id={{ row.target_user_id }}</div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="变更" min-width="260">
              <template #default="{ row }">
                <span class="change-text">{{ summarizeChange(row) || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="request_ip" label="IP" width="140" />
            <el-table-column label="详情" width="90" fixed="right">
              <template #default="{ row }">
                <el-button link type="primary" @click="openDetail(row)">查看</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="userAdminQuery.page"
              v-model:page-size="userAdminQuery.page_size"
              :total="userAdminTotal"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next, jumper"
              background
              @current-change="fetchUserAdminLogs"
              @size-change="fetchUserAdminLogs"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="登录日志" name="login">
          <div class="filter-bar">
            <el-input
              v-model="loginQuery.username"
              placeholder="用户名"
              clearable
              class="filter-item"
              @keyup.enter="handleLoginSearch"
              @clear="handleLoginSearch"
            />
            <el-input
              v-model="loginQuery.ip"
              placeholder="IP地址"
              clearable
              class="filter-item"
              @keyup.enter="handleLoginSearch"
              @clear="handleLoginSearch"
            />
            <el-input
              v-model="loginQuery.device"
              placeholder="设备信息"
              clearable
              class="filter-item"
              @keyup.enter="handleLoginSearch"
              @clear="handleLoginSearch"
            />
            <el-date-picker
              v-model="loginQuery.timeRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              value-format="YYYY-MM-DDTHH:mm:ss"
              class="filter-item date-range"
            />
            <div class="filter-actions">
              <el-button type="primary" @click="handleLoginSearch">查询</el-button>
              <el-button @click="resetLoginFilter">重置</el-button>
            </div>
          </div>

          <el-table :data="loginTableData" border stripe style="width: 100%" v-loading="loginLoading">
            <el-table-column prop="created_at" label="登录时间" width="190">
              <template #default="{ row }">
                {{ formatTime(row.created_at) }}
              </template>
            </el-table-column>
            <el-table-column prop="username" label="用户" width="160" />
            <el-table-column prop="ip" label="IP地址" width="150" />
            <el-table-column prop="device" label="设备信息" min-width="220" />
            <el-table-column prop="user_agent" label="浏览器信息" min-width="260" show-overflow-tooltip />
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="loginQuery.page"
              v-model:page-size="loginQuery.page_size"
              :total="loginTotal"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next, jumper"
              background
              @current-change="fetchLoginLogs"
              @size-change="fetchLoginLogs"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="设备/位置审计" name="device">
          <div class="filter-bar">
            <el-input
              v-model="deviceQuery.device_id"
              placeholder="设备ID"
              clearable
              class="filter-item"
              @keyup.enter="handleDeviceSearch"
              @clear="handleDeviceSearch"
            />
            <el-input
              v-model="deviceQuery.device_name"
              placeholder="设备名称"
              clearable
              class="filter-item"
              @keyup.enter="handleDeviceSearch"
              @clear="handleDeviceSearch"
            />
            <el-input
              v-model="deviceQuery.change_type"
              placeholder="审计类型（如 update_location）"
              clearable
              class="filter-item"
              @keyup.enter="handleDeviceSearch"
              @clear="handleDeviceSearch"
            />
            <el-input
              v-model="deviceQuery.changed_by"
              placeholder="操作人"
              clearable
              class="filter-item"
              @keyup.enter="handleDeviceSearch"
              @clear="handleDeviceSearch"
            />
            <el-date-picker
              v-model="deviceQuery.timeRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              value-format="YYYY-MM-DDTHH:mm:ss"
              class="filter-item date-range"
            />
            <div class="filter-actions">
              <el-button type="primary" @click="handleDeviceSearch">查询</el-button>
              <el-button @click="resetDeviceFilter">重置</el-button>
            </div>
          </div>

          <el-table :data="deviceTableData" border stripe style="width: 100%" v-loading="deviceLoading">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="audit-expand">
                  <div class="audit-expand-col">
                    <div class="audit-expand-title">旧值</div>
                    <pre class="audit-json">{{ formatDetailJson(row.old_values) }}</pre>
                  </div>
                  <div class="audit-expand-col">
                    <div class="audit-expand-title">新值</div>
                    <pre class="audit-json">{{ formatDetailJson(row.new_values) }}</pre>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="changed_at" label="时间" width="190">
              <template #default="{ row }">
                {{ formatTime(row.changed_at) }}
              </template>
            </el-table-column>
            <el-table-column prop="device_id" label="设备ID" width="100" />
            <el-table-column prop="device_name" label="设备名称" width="180" />
            <el-table-column prop="change_type" label="类型" width="170" />
            <el-table-column prop="changed_by_name" label="操作人" width="150">
              <template #default="{ row }">
                {{ row.changed_by_name || row.changed_by || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="change_description" label="描述" min-width="260" />
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="deviceQuery.page"
              v-model:page-size="deviceQuery.page_size"
              :total="deviceTotal"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next, jumper"
              background
              @current-change="fetchDeviceLogs"
              @size-change="fetchDeviceLogs"
            />
          </div>
        </el-tab-pane>

        <el-tab-pane label="WebSSH审计" name="ssh">
          <div class="filter-bar">
            <el-input
              v-model="sshQuery.device_id"
              placeholder="设备ID"
              clearable
              class="filter-item"
              @keyup.enter="handleSshSearch"
              @clear="handleSshSearch"
            />
            <el-input
              v-model="sshQuery.device_name"
              placeholder="设备名称"
              clearable
              class="filter-item"
              @keyup.enter="handleSshSearch"
              @clear="handleSshSearch"
            />
            <el-input
              v-model="sshQuery.executed_by"
              placeholder="操作人"
              clearable
              class="filter-item"
              @keyup.enter="handleSshSearch"
              @clear="handleSshSearch"
            />
            <el-input
              v-model="sshQuery.command"
              placeholder="命令关键词"
              clearable
              class="filter-item"
              @keyup.enter="handleSshSearch"
              @clear="handleSshSearch"
            />
            <el-date-picker
              v-model="sshQuery.timeRange"
              type="datetimerange"
              range-separator="至"
              start-placeholder="开始时间"
              end-placeholder="结束时间"
              value-format="YYYY-MM-DDTHH:mm:ss"
              class="filter-item date-range"
            />
            <div class="filter-actions">
              <el-button type="primary" @click="handleSshSearch">查询</el-button>
              <el-button @click="resetSshFilter">重置</el-button>
            </div>
          </div>

          <el-table :data="sshTableData" border stripe style="width: 100%" v-loading="sshLoading">
            <el-table-column prop="executed_at" label="时间" width="190">
              <template #default="{ row }">
                {{ formatTime(row.executed_at) }}
              </template>
            </el-table-column>
            <el-table-column prop="device_id" label="设备ID" width="100" />
            <el-table-column prop="device_name" label="设备名称" width="180" />
            <el-table-column prop="device_ip" label="设备IP" width="150" />
            <el-table-column prop="executed_by_name" label="操作人" width="150">
              <template #default="{ row }">
                {{ row.executed_by_name || row.executed_by || '-' }}
              </template>
            </el-table-column>
            <el-table-column prop="command" label="命令" min-width="300" />
          </el-table>

          <div class="pagination">
            <el-pagination
              v-model:current-page="sshQuery.page"
              v-model:page-size="sshQuery.page_size"
              :total="sshTotal"
              :page-sizes="[20, 50, 100, 200]"
              layout="total, sizes, prev, pager, next, jumper"
              background
              @current-change="fetchSshLogs"
              @size-change="fetchSshLogs"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-dialog v-model="detailDialogVisible" title="审计详情" width="720px" append-to-body>
      <div class="detail-grid" v-if="detailRow">
        <div class="detail-row">
          <span class="detail-label">时间</span>
          <span class="detail-value">{{ formatTime(detailRow.created_at) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">操作者</span>
          <span class="detail-value">{{ detailRow.actor_username || '-' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">动作</span>
          <span class="detail-value">{{ detailRow.action_label || detailRow.action || '-' }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">目标</span>
          <span class="detail-value">{{ formatTarget(detailRow) }}</span>
        </div>
        <div class="detail-row">
          <span class="detail-label">IP</span>
          <span class="detail-value">{{ detailRow.request_ip || '-' }}</span>
        </div>
        <div class="detail-row" v-if="summarizeChange(detailRow)">
          <span class="detail-label">变更</span>
          <span class="detail-value">{{ summarizeChange(detailRow) }}</span>
        </div>
      </div>
      <el-divider />
      <el-input
        type="textarea"
        :rows="16"
        :readonly="true"
        :model-value="formatDetailJson(detailRow?.detail)"
      />
      <template #footer>
        <el-button @click="detailDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';

const activeTab = ref('user-admin');
const detailDialogVisible = ref(false);
const detailRow = ref(null);

const userAdminLoading = ref(false);
const userAdminTableData = ref([]);
const userAdminTotal = ref(0);
const userAdminQuery = reactive({
  page: 1,
  page_size: 50,
  actor_username: '',
  action: '',
  target_type: '',
  target_user_id: '',
  timeRange: null
});

const loginLoading = ref(false);
const loginTableData = ref([]);
const loginTotal = ref(0);
const loginQuery = reactive({
  page: 1,
  page_size: 50,
  username: '',
  ip: '',
  device: '',
  timeRange: null
});

const deviceLoading = ref(false);
const deviceTableData = ref([]);
const deviceTotal = ref(0);
const deviceQuery = reactive({
  page: 1,
  page_size: 50,
  device_id: '',
  device_name: '',
  change_type: '',
  changed_by: '',
  timeRange: null
});

const sshLoading = ref(false);
const sshTableData = ref([]);
const sshTotal = ref(0);
const sshQuery = reactive({
  page: 1,
  page_size: 50,
  device_id: '',
  device_name: '',
  executed_by: '',
  command: '',
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

const normalizeDetail = (detail) => {
  if (!detail) return null;
  if (typeof detail === 'object') return detail;
  if (typeof detail === 'string') {
    try {
      return JSON.parse(detail);
    } catch {
      return { raw: detail };
    }
  }
  return { raw: String(detail) };
};

const formatDetailJson = (detail) => {
  const d = normalizeDetail(detail);
  if (!d) return '';
  try {
    return JSON.stringify(d, null, 2);
  } catch {
    return String(detail);
  }
};

const formatTarget = (row) => {
  if (!row) return '-';
  const t = String(row.target_type || '').trim();
  const id = row.target_id ?? null;
  const label = String(row.target_label || '').trim();
  if (t) {
    const parts = [t];
    if (label) parts.push(label);
    if (id !== null && id !== undefined && id !== '') parts.push(`id=${id}`);
    return parts.join(' ');
  }
  if (row.target_user_id !== null && row.target_user_id !== undefined && row.target_user_id !== '') {
    return `user id=${row.target_user_id}`;
  }
  return '-';
};

const summarizeChange = (row) => {
  const d = normalizeDetail(row?.detail);
  if (!d) return '';
  const parts = [];
  const pushList = (label, arr) => {
    const a = Array.isArray(arr) ? arr.filter(Boolean) : [];
    if (a.length) parts.push(`${label}(${a.length}) ${a.slice(0, 6).join(', ')}${a.length > 6 ? '...' : ''}`);
  };

  pushList('新增权限', d.added_permission_codes || d.added_permissions);
  pushList('移除权限', d.removed_permission_codes || d.removed_permissions);
  pushList('新增角色', d.added_role_codes);
  pushList('移除角色', d.removed_role_codes);

  if (d.before_default || d.after_default) {
    const b = d.before_default ? (d.before_default.code || d.before_default.id) : '-';
    const a = d.after_default ? (d.after_default.code || d.after_default.id) : '-';
    parts.push(`默认角色 ${b} -> ${a}`);
  }

  if (parts.length) return parts.join('；');
  if (d.before && d.after) return '存在变更前/后快照';
  if (d.role || d.permission) return '对象信息变更';
  return '';
};

const openDetail = (row) => {
  detailRow.value = row || null;
  detailDialogVisible.value = true;
};

const fetchUserAdminLogs = async () => {
  userAdminLoading.value = true;
  try {
    const params = {
      page: userAdminQuery.page,
      page_size: userAdminQuery.page_size,
      actor_username: userAdminQuery.actor_username || undefined,
      action: userAdminQuery.action || undefined
    };
    if (userAdminQuery.target_type) params.target_type = String(userAdminQuery.target_type).trim();
    if (userAdminQuery.target_user_id) {
      const n = Number(userAdminQuery.target_user_id);
      if (!Number.isNaN(n)) params.target_user_id = n;
    }
    if (Array.isArray(userAdminQuery.timeRange) && userAdminQuery.timeRange.length === 2) {
      params.start_at = userAdminQuery.timeRange[0];
      params.end_at = userAdminQuery.timeRange[1];
    }
    const res = await axios.get('/api/v1/system/audit/user-admin', { params });
    if (res.data?.code === 200) {
      userAdminTableData.value = res.data.data || [];
      userAdminTotal.value = res.data.meta?.total || 0;
      return;
    }
    ElMessage.error(res.data?.message || '获取系统操作审计失败');
  } catch {
    ElMessage.error('获取系统操作审计失败');
  } finally {
    userAdminLoading.value = false;
  }
};

const fetchLoginLogs = async () => {
  loginLoading.value = true;
  try {
    const params = {
      page: loginQuery.page,
      page_size: loginQuery.page_size,
      username: loginQuery.username || undefined,
      ip: loginQuery.ip || undefined,
      device: loginQuery.device || undefined
    };
    if (Array.isArray(loginQuery.timeRange) && loginQuery.timeRange.length === 2) {
      params.start_at = loginQuery.timeRange[0];
      params.end_at = loginQuery.timeRange[1];
    }
    const res = await axios.get('/api/v1/system/audit/login-logs', { params });
    if (res.data?.code === 200) {
      loginTableData.value = res.data.data || [];
      loginTotal.value = res.data.meta?.total || 0;
      return;
    }
    ElMessage.error(res.data?.message || '获取登录日志失败');
  } catch {
    ElMessage.error('获取登录日志失败');
  } finally {
    loginLoading.value = false;
  }
};

const fetchDeviceLogs = async () => {
  deviceLoading.value = true;
  try {
    const params = {
      page: deviceQuery.page,
      page_size: deviceQuery.page_size,
      device_name: deviceQuery.device_name || undefined,
      change_type: deviceQuery.change_type || undefined,
      changed_by: deviceQuery.changed_by || undefined
    };
    if (deviceQuery.device_id) {
      const n = Number(deviceQuery.device_id);
      if (!Number.isNaN(n)) params.device_id = n;
    }
    if (Array.isArray(deviceQuery.timeRange) && deviceQuery.timeRange.length === 2) {
      params.start_at = deviceQuery.timeRange[0];
      params.end_at = deviceQuery.timeRange[1];
    }
    const res = await axios.get('/api/v1/system/audit/device-changes', { params });
    if (res.data?.code === 200) {
      deviceTableData.value = res.data.data || [];
      deviceTotal.value = res.data.meta?.total || 0;
      return;
    }
    ElMessage.error(res.data?.message || '获取设备/位置审计失败');
  } catch {
    ElMessage.error('获取设备/位置审计失败');
  } finally {
    deviceLoading.value = false;
  }
};

const fetchSshLogs = async () => {
  sshLoading.value = true;
  try {
    const params = {
      page: sshQuery.page,
      page_size: sshQuery.page_size,
      device_name: sshQuery.device_name || undefined,
      executed_by: sshQuery.executed_by || undefined,
      command: sshQuery.command || undefined
    };
    if (sshQuery.device_id) {
      const n = Number(sshQuery.device_id);
      if (!Number.isNaN(n)) params.device_id = n;
    }
    if (Array.isArray(sshQuery.timeRange) && sshQuery.timeRange.length === 2) {
      params.start_at = sshQuery.timeRange[0];
      params.end_at = sshQuery.timeRange[1];
    }
    const res = await axios.get('/api/v1/system/audit/ssh-commands', { params });
    if (res.data?.code === 200) {
      sshTableData.value = res.data.data || [];
      sshTotal.value = res.data.meta?.total || 0;
      return;
    }
    ElMessage.error(res.data?.message || '获取WebSSH审计失败');
  } catch {
    ElMessage.error('获取WebSSH审计失败');
  } finally {
    sshLoading.value = false;
  }
};

const handleUserAdminSearch = async () => {
  userAdminQuery.page = 1;
  await fetchUserAdminLogs();
};

const resetUserAdminFilter = async () => {
  userAdminQuery.page = 1;
  userAdminQuery.page_size = 50;
  userAdminQuery.actor_username = '';
  userAdminQuery.action = '';
  userAdminQuery.target_type = '';
  userAdminQuery.target_user_id = '';
  userAdminQuery.timeRange = null;
  await fetchUserAdminLogs();
};

const handleLoginSearch = async () => {
  loginQuery.page = 1;
  await fetchLoginLogs();
};

const resetLoginFilter = async () => {
  loginQuery.page = 1;
  loginQuery.page_size = 50;
  loginQuery.username = '';
  loginQuery.ip = '';
  loginQuery.device = '';
  loginQuery.timeRange = null;
  await fetchLoginLogs();
};

const handleDeviceSearch = async () => {
  deviceQuery.page = 1;
  await fetchDeviceLogs();
};

const resetDeviceFilter = async () => {
  deviceQuery.page = 1;
  deviceQuery.page_size = 50;
  deviceQuery.device_id = '';
  deviceQuery.device_name = '';
  deviceQuery.change_type = '';
  deviceQuery.changed_by = '';
  deviceQuery.timeRange = null;
  await fetchDeviceLogs();
};

const handleSshSearch = async () => {
  sshQuery.page = 1;
  await fetchSshLogs();
};

const resetSshFilter = async () => {
  sshQuery.page = 1;
  sshQuery.page_size = 50;
  sshQuery.device_id = '';
  sshQuery.device_name = '';
  sshQuery.executed_by = '';
  sshQuery.command = '';
  sshQuery.timeRange = null;
  await fetchSshLogs();
};

const handleTabChange = async (name) => {
  if (name === 'user-admin' && userAdminTableData.value.length === 0) await fetchUserAdminLogs();
  if (name === 'login' && loginTableData.value.length === 0) await fetchLoginLogs();
  if (name === 'device' && deviceTableData.value.length === 0) await fetchDeviceLogs();
  if (name === 'ssh' && sshTableData.value.length === 0) await fetchSshLogs();
};

onMounted(async () => {
  await fetchUserAdminLogs();
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
  color: #111827;
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

.target-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.2;
}

.target-main {
  font-weight: 600;
}

.target-sub {
  margin-top: 2px;
  font-size: 12px;
  color: #6b7280;
}

.change-text {
  color: #374151;
}

.audit-expand {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}

.audit-expand-col {
  min-width: 0;
}

.audit-expand-title {
  font-weight: 600;
  margin-bottom: 6px;
  color: #374151;
}

.audit-json {
  margin: 0;
  padding: 10px;
  background: #f9fafb;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 260px;
  overflow: auto;
}

.detail-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 10px;
}

.detail-row {
  display: flex;
  gap: 10px;
}

.detail-label {
  width: 80px;
  color: #6b7280;
}

.detail-value {
  color: #111827;
  word-break: break-all;
}

@media (max-width: 900px) {
  .filter-item {
    max-width: 100%;
    width: 100%;
  }

  .date-range {
    max-width: 100%;
  }

  .audit-expand {
    grid-template-columns: 1fr;
  }
}
</style>
