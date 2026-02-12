<template>
  <div class="user-manage-page" :class="{ 'is-mobile': isMobile }">
    <!-- Header -->
    <div class="page-header">
      <div class="header-content">
        <div class="header-title">
          <h2>用户管理</h2>
          <span class="subtitle" v-if="!isMobile">系统用户账号与权限管理</span>
        </div>
        <div class="header-actions">
          <el-button type="primary" :icon="Plus" @click="openCreate" :circle="isMobile">
            <span v-if="!isMobile">新建用户</span>
          </el-button>
        </div>
      </div>
    </div>

    <!-- Filter & Content -->
    <div class="main-content">
      <!-- Filter Bar -->
      <div class="filter-wrapper">
        <div class="filter-left">
          <el-input
            v-model="query.q"
            placeholder="搜索用户名/昵称/邮箱"
            :prefix-icon="Search"
            clearable
            class="search-input"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          />
          <el-select 
            v-model="query.is_approved" 
            placeholder="状态" 
            clearable 
            class="status-select"
            @change="handleSearch"
          >
            <el-option :value="true" label="启用" />
            <el-option :value="false" label="封禁" />
          </el-select>
        </div>
        <div class="filter-right" v-if="!isMobile">
          <el-button :icon="Search" type="primary" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="resetFilter">重置</el-button>
        </div>
      </div>

      <!-- Loading State -->
      <div v-loading="loading" class="data-container">
        <!-- Mobile: Card List View -->
        <div v-if="isMobile" class="mobile-list">
          <el-empty v-if="tableData.length === 0" description="暂无用户数据" />
          <div v-else class="user-card" v-for="user in tableData" :key="user.id" @click="openDetail(user)">
            <div class="card-header">
              <div class="user-info">
                <el-avatar :size="40" :src="user.avatar || ''" class="user-avatar">
                  {{ (user.nickname || user.username || '?').charAt(0).toUpperCase() }}
                </el-avatar>
                <div class="user-meta">
                  <div class="name-row">
                    <span class="username">{{ user.username }}</span>
                    <el-tag size="small" :type="user.is_approved ? 'success' : 'danger'" effect="dark" class="status-tag">
                      {{ user.is_approved ? '启用' : '封禁' }}
                    </el-tag>
                  </div>
                  <div class="sub-row">{{ user.nickname || '无昵称' }}</div>
                </div>
              </div>
              <div class="card-more">
                <el-dropdown trigger="click" @command="(cmd) => handleCommand(cmd, user)">
                  <el-icon class="more-icon"><MoreFilled /></el-icon>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item command="edit" :icon="Edit">编辑</el-dropdown-item>
                      <el-dropdown-item command="toggle" :icon="SwitchButton">{{ user.is_approved ? '封禁账号' : '解封账号' }}</el-dropdown-item>
                      <el-dropdown-item command="reset" :icon="Key">重置密码</el-dropdown-item>
                      <el-dropdown-item command="delete" :icon="Delete" divided style="color: var(--el-color-danger)">删除用户</el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
            <div class="card-body">
              <div class="info-item">
                <el-icon><Message /></el-icon>
                <span>{{ user.email || '未绑定邮箱' }}</span>
              </div>
              <div class="info-item">
                <el-icon><Calendar /></el-icon>
                <span>ID: {{ user.id }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- PC: Table View -->
        <el-table
          v-else
          :data="tableData"
          style="width: 100%"
          @selection-change="handleSelectionChange"
          class="custom-table"
        >
          <el-table-column type="selection" width="50" />
          <el-table-column prop="id" label="ID" width="80" sortable />
          <el-table-column label="用户" min-width="200">
            <template #default="{ row }">
              <div class="table-user-cell">
                <el-avatar :size="32" class="mr-3">{{ (row.nickname || row.username).charAt(0).toUpperCase() }}</el-avatar>
                <div class="user-texts">
                  <div class="u-name">{{ row.username }}</div>
                  <div class="u-nick">{{ row.nickname }}</div>
                </div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="icon-text">
                <el-icon><Message /></el-icon>
                <span>{{ row.email || '-' }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="状态" width="100" align="center">
            <template #default="{ row }">
              <el-switch
                v-model="row.is_approved"
                inline-prompt
                active-text="启用"
                inactive-text="封禁"
                :loading="saving"
                @change="() => toggleStatus(row, true)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" align="right" fixed="right">
            <template #default="{ row }">
              <el-tooltip content="编辑" placement="top">
                <el-button link type="primary" :icon="Edit" @click="openEdit(row)" />
              </el-tooltip>
              <el-tooltip content="重置密码" placement="top">
                <el-button link type="warning" :icon="Key" @click="openResetPwd(row)" />
              </el-tooltip>
              <el-tooltip content="删除" placement="top">
                <el-button link type="danger" :icon="Delete" @click="handleDelete(row)" />
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Pagination -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[20, 50, 100]"
          :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          :small="isMobile"
          background
          @current-change="fetchUsers"
          @size-change="fetchUsers"
        />
      </div>
    </div>

    <!-- Dialogs (Responsive) -->
    <el-dialog v-model="createVisible" title="新建用户" :width="isMobile ? '90%' : '500px'" class="custom-dialog">
      <el-form :model="createForm" label-position="top" size="large">
        <el-form-item label="用户名" required>
          <el-input v-model="createForm.username" placeholder="登录账号" :prefix-icon="User" />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="createForm.nickname" placeholder="显示名称" :prefix-icon="UserFilled" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="createForm.email" placeholder="联系邮箱" :prefix-icon="Message" />
        </el-form-item>
        <el-form-item label="初始密码" required>
          <el-input v-model="createForm.password" type="password" show-password placeholder="设置密码" :prefix-icon="Lock" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">确认创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑用户" :width="isMobile ? '90%' : '500px'" class="custom-dialog">
      <el-form :model="editForm" label-position="top" size="large">
        <el-form-item label="昵称">
          <el-input v-model="editForm.nickname" placeholder="显示名称" :prefix-icon="UserFilled" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="联系邮箱" :prefix-icon="Message" />
        </el-form-item>
        <div class="form-row">
          <el-form-item label="邮件通知">
            <el-switch v-model="editForm.is_email_notify" />
          </el-form-item>
          <el-form-item label="账号状态">
            <el-switch v-model="editForm.is_approved" active-text="启用" inactive-text="封禁" />
          </el-form-item>
        </div>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存修改</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="用户详情" :width="isMobile ? '90%' : '500px'" class="custom-dialog">
      <div v-if="detailData" class="user-detail-view">
        <div class="detail-header">
          <el-avatar :size="60" class="detail-avatar">{{ (detailData.nickname || detailData.username).charAt(0).toUpperCase() }}</el-avatar>
          <div class="detail-info">
            <h3>{{ detailData.username }}</h3>
            <p>{{ detailData.nickname || '未设置昵称' }}</p>
          </div>
        </div>
        <div class="detail-list">
          <div class="detail-item">
            <span class="label">ID</span>
            <span class="value">{{ detailData.id }}</span>
          </div>
          <div class="detail-item">
            <span class="label">邮箱</span>
            <span class="value">{{ detailData.email || '-' }}</span>
          </div>
          <div class="detail-item">
            <span class="label">状态</span>
            <el-tag size="small" :type="detailData.is_approved ? 'success' : 'danger'">{{ detailData.is_approved ? '正常' : '封禁' }}</el-tag>
          </div>
          <div class="detail-item vertical">
            <span class="label">角色权限</span>
            <div class="role-tags">
              <el-tag v-for="r in (detailData.roles || [])" :key="r.id" size="small" effect="plain">{{ r.name }}</el-tag>
              <span v-if="!detailData.roles || detailData.roles.length === 0" class="empty-text">暂无角色</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetPwdVisible" title="重置密码" :width="isMobile ? '90%' : '400px'" class="custom-dialog">
      <div v-if="resetPwdUser" class="reset-tip">
        <el-icon class="warn-icon"><WarningFilled /></el-icon>
        <span>正在重置 <b>{{ resetPwdUser.username }}</b> 的密码</span>
      </div>
      <el-form :model="resetPwdForm" label-position="top" size="large" @submit.prevent>
        <el-form-item label="新密码">
          <el-input 
            v-model="resetPwdForm.password" 
            type="password" 
            show-password 
            placeholder="请输入新密码" 
            :prefix-icon="Lock"
            @keyup.enter="submitResetPwd" 
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitResetPwd">确认重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, onBeforeUnmount, reactive, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { 
  Search, Plus, Refresh, Edit, Delete, Key, 
  User, UserFilled, Message, Lock, MoreFilled, 
  SwitchButton, Calendar, WarningFilled
} from '@element-plus/icons-vue';

// Mobile Detection
const isMobile = ref(window.innerWidth < 768);
const handleResize = () => {
  isMobile.value = window.innerWidth < 768;
};

// Data
const loading = ref(false);
const saving = ref(false);
const tableData = ref([]);
const total = ref(0);
const selectedUserIds = ref([]);

const query = reactive({
  q: '',
  is_approved: undefined,
  page: 1,
  page_size: 20
});

// Dialog States
const createVisible = ref(false);
const editVisible = ref(false);
const detailVisible = ref(false);
const resetPwdVisible = ref(false);

// Forms
const createForm = reactive({ username: '', nickname: '', email: '', password: '' });
const editUserId = ref(null);
const editForm = reactive({ nickname: '', email: '', is_email_notify: false, is_approved: true });
const detailData = ref(null);
const resetPwdUser = ref(null);
const resetPwdForm = reactive({ password: '' });

// Methods
const fetchUsers = async () => {
  loading.value = true;
  try {
    const params = {
      q: query.q,
      is_approved: query.is_approved,
      page: query.page,
      page_size: query.page_size
    };
    const res = await axios.get('/api/v1/users', { params });
    if (res.data?.code === 200) {
      tableData.value = res.data.data || [];
      total.value = res.data.meta?.total || 0;
    } else {
      ElMessage.error(res.data?.message || '获取用户列表失败');
    }
  } catch (e) {
    ElMessage.error('获取用户列表失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  query.page = 1;
  fetchUsers();
};

const resetFilter = () => {
  query.q = '';
  query.is_approved = undefined;
  query.page = 1;
  handleSearch();
};

const handleSelectionChange = (rows) => {
  selectedUserIds.value = Array.isArray(rows) ? rows.map(r => r.id) : [];
};

// Create
const openCreate = () => {
  createForm.username = '';
  createForm.nickname = '';
  createForm.email = '';
  createForm.password = '';
  createVisible.value = true;
};

const submitCreate = async () => {
  if (!createForm.username || !createForm.password) {
    ElMessage.warning('用户名与密码不能为空');
    return;
  }
  saving.value = true;
  try {
    const payload = { ...createForm };
    if (!payload.nickname) delete payload.nickname;
    if (!payload.email) delete payload.email;
    
    const res = await axios.post('/api/v1/users', payload);
    if (res.data?.code === 200) {
      ElMessage.success('创建成功');
      createVisible.value = false;
      fetchUsers();
    } else {
      ElMessage.error(res.data?.message || '创建失败');
    }
  } catch (e) {
    ElMessage.error('创建失败');
  } finally {
    saving.value = false;
  }
};

// Edit
const openEdit = (row) => {
  editUserId.value = row.id;
  editForm.nickname = row.nickname || '';
  editForm.email = row.email || '';
  editForm.is_email_notify = Boolean(row.is_email_notify);
  editForm.is_approved = Boolean(row.is_approved);
  editVisible.value = true;
};

const submitEdit = async () => {
  if (!editUserId.value) return;
  saving.value = true;
  try {
    const res = await axios.put(`/api/v1/users/${editUserId.value}`, editForm);
    if (res.data?.code === 200) {
      ElMessage.success('保存成功');
      editVisible.value = false;
      fetchUsers();
    } else {
      ElMessage.error(res.data?.message || '保存失败');
    }
  } catch (e) {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
};

// Status
const toggleStatus = async (row, isSwitch = false) => {
  // If triggered by switch, we might want to skip confirmation or handle it differently
  // But for safety, let's keep it or just do it if it's a switch
  if (!isSwitch) {
    try {
      await ElMessageBox.confirm(
        row.is_approved ? '确认封禁该用户？' : '确认解封该用户？',
        '提示', { type: 'warning' }
      );
    } catch { return; }
  }
  
  saving.value = true;
  try {
    // If it was a switch click, the v-model already updated the row.is_approved
    // But our API expects the *new* state. 
    // If we use v-model on switch, row.is_approved is already the target value.
    // If we clicked a button, we pass !row.is_approved
    const targetStatus = isSwitch ? row.is_approved : !row.is_approved;
    
    const res = await axios.post('/api/v1/users/status', { user_id: row.id, is_approved: targetStatus });
    if (res.data?.code === 200) {
      if (!isSwitch) ElMessage.success('操作成功');
      // If switch, no need to refresh entire list, just success
      if (!isSwitch) fetchUsers(); 
    } else {
      ElMessage.error(res.data?.message || '操作失败');
      if (isSwitch) row.is_approved = !row.is_approved; // revert
    }
  } catch (e) {
    ElMessage.error('操作失败');
    if (isSwitch) row.is_approved = !row.is_approved; // revert
  } finally {
    saving.value = false;
  }
};

// Delete
const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该用户？此操作不可恢复。', '警告', { type: 'warning', confirmButtonClass: 'el-button--danger' });
  } catch { return; }
  
  saving.value = true;
  try {
    const res = await axios.delete(`/api/v1/users/${row.id}`);
    if (res.data?.code === 200) {
      ElMessage.success('删除成功');
      fetchUsers();
    } else {
      ElMessage.error(res.data?.message || '删除失败');
    }
  } catch (e) {
    ElMessage.error('删除失败');
  } finally {
    saving.value = false;
  }
};

// Reset Password
const openResetPwd = (row) => {
  resetPwdUser.value = row;
  resetPwdForm.password = '';
  resetPwdVisible.value = true;
};

const submitResetPwd = async () => {
  if (!resetPwdUser.value?.id || !resetPwdForm.password) {
    ElMessage.warning('请输入新密码');
    return;
  }
  saving.value = true;
  try {
    const res = await axios.put(`/api/v1/users/${resetPwdUser.value.id}/password`, { password: resetPwdForm.password });
    if (res.data?.code === 200) {
      ElMessage.success('重置成功');
      resetPwdVisible.value = false;
    } else {
      ElMessage.error(res.data?.message || '重置失败');
    }
  } catch (e) {
    ElMessage.error('重置失败');
  } finally {
    saving.value = false;
  }
};

// Detail
const openDetail = async (row) => {
  detailVisible.value = true;
  detailData.value = { ...row, roles: [] }; // optimistically show basic info
  try {
    const res = await axios.get(`/api/v1/users/${row.id}`);
    if (res.data?.code === 200) {
      detailData.value = res.data.data;
    }
  } catch (e) {
    // silent fail
  }
};

// Mobile Action Sheet Handler
const handleCommand = (cmd, user) => {
  if (cmd === 'edit') openEdit(user);
  if (cmd === 'toggle') toggleStatus(user, false);
  if (cmd === 'reset') openResetPwd(user);
  if (cmd === 'delete') handleDelete(user);
};

// Lifecycle
onMounted(() => {
  window.addEventListener('resize', handleResize);
  fetchUsers();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
});
</script>

<style scoped>
/* Page Layout */
.user-manage-page {
  padding: 24px;
  background-color: #f5f7fa;
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.user-manage-page.is-mobile {
  padding: 16px;
  background-color: #ffffff;
}

/* Header */
.page-header {
  margin-bottom: 24px;
}

.header-content {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-title h2 {
  font-size: 24px;
  color: #1f2f3d;
  margin: 0;
  font-weight: 600;
}

.header-title .subtitle {
  font-size: 14px;
  color: #909399;
  margin-top: 4px;
  display: block;
}

/* Main Content */
.main-content {
  flex: 1;
  display: flex;
  flex-direction: column;
}

/* Filter Bar */
.filter-wrapper {
  background: #fff;
  padding: 16px;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
  flex-wrap: wrap;
  gap: 12px;
}

.is-mobile .filter-wrapper {
  padding: 0;
  box-shadow: none;
  background: transparent;
  margin-bottom: 12px;
}

.filter-left {
  display: flex;
  gap: 12px;
  flex: 1;
}

.search-input {
  max-width: 300px;
}

.is-mobile .search-input {
  max-width: 100%;
  flex: 1;
}

.status-select {
  width: 120px;
}

/* Data Container */
.data-container {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
  overflow: hidden;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.is-mobile .data-container {
  background: transparent;
  box-shadow: none;
  border-radius: 0;
  overflow: visible;
}

/* Mobile Card List */
.mobile-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.user-card {
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  border: 1px solid #ebeef5;
  transition: all 0.2s;
}

.user-card:active {
  background-color: #fafafa;
  transform: scale(0.99);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 12px;
}

.user-info {
  display: flex;
  gap: 12px;
  align-items: center;
}

.user-avatar {
  background: #409eff;
  font-weight: 600;
  font-size: 16px;
}

.user-meta {
  display: flex;
  flex-direction: column;
}

.name-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.username {
  font-weight: 600;
  font-size: 16px;
  color: #303133;
}

.sub-row {
  font-size: 12px;
  color: #909399;
  margin-top: 2px;
}

.card-more {
  color: #909399;
  padding: 4px;
}

.more-icon {
  font-size: 20px;
}

.card-body {
  background: #f8f9fa;
  border-radius: 8px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.info-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: #606266;
}

/* PC Table Styles */
.custom-table {
  --el-table-header-bg-color: #f5f7fa;
}

.table-user-cell {
  display: flex;
  align-items: center;
}

.user-texts {
  margin-left: 10px;
  display: flex;
  flex-direction: column;
}

.u-name {
  font-weight: 500;
  font-size: 14px;
}

.u-nick {
  font-size: 12px;
  color: #909399;
}

.icon-text {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #606266;
}

/* Pagination */
.pagination-wrapper {
  padding: 16px;
  display: flex;
  justify-content: flex-end;
  border-top: 1px solid #ebeef5;
}

.is-mobile .pagination-wrapper {
  justify-content: center;
  background: transparent;
  border: none;
  padding: 20px 0;
}

/* Dialog Customization */
.custom-dialog {
  border-radius: 12px;
}

.form-row {
  display: flex;
  gap: 20px;
}

.form-row .el-form-item {
  flex: 1;
}

.user-detail-view {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.detail-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding-bottom: 20px;
  border-bottom: 1px solid #ebeef5;
}

.detail-avatar {
  background: #409eff;
  font-size: 24px;
}

.detail-info h3 {
  margin: 0;
  font-size: 20px;
  color: #303133;
}

.detail-info p {
  margin: 4px 0 0;
  color: #909399;
}

.detail-list {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}

.detail-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-item.vertical {
  grid-column: span 2;
}

.detail-item .label {
  font-size: 12px;
  color: #909399;
}

.detail-item .value {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.role-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.empty-text {
  font-size: 13px;
  color: #c0c4cc;
}

.reset-tip {
  display: flex;
  align-items: center;
  gap: 8px;
  background: #fdf6ec;
  padding: 10px 16px;
  border-radius: 4px;
  color: #e6a23c;
  margin-bottom: 20px;
  font-size: 13px;
}

.warn-icon {
  font-size: 16px;
}
</style>
