<template>
  <div class="rbac-container">
    <div class="rbac-header">
      <div class="page-title">
        <el-icon class="mr-2"><User /></el-icon>
        <span>角色人员分布</span>
        <el-tooltip content="查看和管理用户角色分配情况" placement="right">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      <div class="header-actions">
        <!-- Optional: Add global actions -->
      </div>
    </div>

    <div class="rbac-content" v-loading="loading">
      <!-- 1. Role Summary Cards -->
      <div class="role-summary-section custom-scrollbar">
        <div 
          v-for="role in roles" 
          :key="role.id" 
          class="role-summary-card"
          :class="{ active: filterRoleId === role.id }"
          @click="toggleRoleFilter(role.id)"
        >
          <div class="role-card-icon">
            <el-icon><UserFilled /></el-icon>
          </div>
          <div class="role-card-info">
            <div class="role-name">{{ role.name }}</div>
            <div class="role-count">{{ role.user_count || 0 }} 人</div>
          </div>
          <el-icon v-if="filterRoleId === role.id" class="check-icon"><Check /></el-icon>
        </div>
      </div>

      <!-- 2. Search and Table -->
      <div class="main-panel">
        <div class="filter-bar">
          <el-input 
            v-model="searchQuery" 
            placeholder="搜索用户名/昵称/邮箱" 
            prefix-icon="Search" 
            clearable 
            class="filter-input"
            @clear="handleSearch"
            @keyup.enter="handleSearch"
          />
          <div class="filter-actions">
            <el-button type="primary" icon="Search" @click="handleSearch">搜索</el-button>
            <el-button icon="Refresh" @click="resetFilter">重置</el-button>
            <el-button 
              type="danger" 
              icon="Delete" 
              :disabled="selectedUserIds.length === 0" 
              @click="handleBatchDelete"
            >
              批量删除
            </el-button>
          </div>
        </div>

        <div v-if="isMobile" class="mobile-list">
          <el-empty v-if="tableData.length === 0" description="暂无数据" />
          <div v-for="item in tableData" :key="item.id" class="user-card">
            <div class="card-header">
              <div class="user-main">
                <span class="username">{{ item.username }}</span>
                <span class="nickname" v-if="item.nickname">({{ item.nickname }})</span>
              </div>
              <el-checkbox 
                :model-value="selectedUserIds.includes(item.id)"
                @change="(val) => handleMobileSelection(item, val)"
              />
            </div>
            <div class="card-body">
              <div class="info-row">
                <span class="label">邮箱:</span>
                <span class="value">{{ item.email || '-' }}</span>
              </div>
              <div class="info-row role-row">
                <span class="label">角色:</span>
                <div class="role-tags">
                   <el-tag 
                    v-for="role in item.roles" 
                    :key="role.id" 
                    size="small" 
                  >
                    {{ role.name }}
                  </el-tag>
                  <span v-if="!item.roles || item.roles.length === 0" class="text-gray-400 text-xs">暂无角色</span>
                </div>
              </div>
            </div>
            <div class="card-actions">
              <el-button size="small" type="primary" link icon="Edit" @click="handleEditUserRoles(item)">分配角色</el-button>
              <el-button size="small" type="primary" link icon="Key" @click="handleResetPassword(item)">重置密码</el-button>
              <el-button size="small" type="danger" link icon="Delete" @click="handleDeleteUser(item)">删除</el-button>
            </div>
          </div>
        </div>

        <div v-else class="table-container">
          <el-table 
            :data="tableData" 
            border 
            stripe 
            style="width: 100%" 
            height="100%"
            @selection-change="handleSelectionChange"
          >
            <el-table-column type="selection" width="55" />
            <el-table-column prop="username" label="用户名" min-width="120" />
            <el-table-column prop="nickname" label="昵称" min-width="120" />
            <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
            <el-table-column label="所属角色" min-width="200">
              <template #default="{ row }">
                <el-tag 
                  v-for="role in row.roles" 
                  :key="role.id" 
                  size="small" 
                  class="mr-1 mb-1"
                >
                  {{ role.name }}
                </el-tag>
                <span v-if="!row.roles || row.roles.length === 0" class="text-gray-400 text-xs">暂无角色</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="280" fixed="right">
              <template #default="{ row }">
                <el-button type="primary" link icon="Edit" @click="handleEditUserRoles(row)">
                  分配角色
                </el-button>
                <el-button type="primary" link icon="Key" @click="handleResetPassword(row)">
                  重置密码
                </el-button>
                <el-button type="danger" link icon="Delete" @click="handleDeleteUser(row)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <div class="pagination-container">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="total"
            :page-sizes="[20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            background
            @size-change="handleSizeChange"
            @current-change="handlePageChange"
          />
        </div>
      </div>
    </div>

    <!-- Edit User Roles Dialog -->
    <el-dialog v-model="editDialogVisible" title="分配角色" width="500px">
      <div v-if="editingUser" class="mb-4">
        <span class="font-bold">当前用户:</span> {{ editingUser.nickname || editingUser.username }}
      </div>
      
      <el-form label-position="top">
        <el-form-item label="选择角色">
          <el-checkbox-group v-model="selectedRoleIds">
            <el-checkbox 
              v-for="role in roles" 
              :key="role.id" 
              :label="role.id"
              :disabled="isProtectedRole(role) && editingUser && currentUserId && Number(editingUser.id) === Number(currentUserId)"
              border
              class="role-checkbox"
            >
              {{ role.name }}
            </el-checkbox>
          </el-checkbox-group>
        </el-form-item>
      </el-form>
      
      <template #footer>
        <el-button @click="editDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="saveUserRoles">保存</el-button>
      </template>
    </el-dialog>

    <!-- Reset Password Dialog -->
    <el-dialog v-model="resetPwdDialogVisible" title="重置密码" :width="isMobile ? '90%' : '400px'">
      <div v-if="currentResetUser" class="mb-4">
        正在为用户 <span class="font-bold">{{ currentResetUser.nickname || currentResetUser.username }}</span> 重置密码
      </div>
      <el-form :model="resetPwdForm" @submit.prevent>
        <el-form-item label="新密码">
          <el-input 
            v-model="resetPwdForm.password" 
            type="password" 
            show-password 
            placeholder="请输入新密码"
            @keyup.enter="submitResetPassword"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="resetting" @click="submitResetPassword">确定重置</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { User, InfoFilled, UserFilled, Check, Search, Refresh, Edit, Delete, Key } from '@element-plus/icons-vue';
import { homeDataStore } from '@/components/home/home/data';

const loading = ref(false);
const roles = ref([]);
const tableData = ref([]);
const total = ref(0);
const currentPage = ref(1);
const pageSize = ref(20);
const searchQuery = ref('');
const filterRoleId = ref(null);
const isMobile = ref(false);

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768;
};

onMounted(() => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
  (async () => {
    try {
      const store = homeDataStore();
      store.syncAuthFromToken();
      const session = await store.ensureSession();
      const id = Number(session?.id);
      currentUserId.value = Number.isFinite(id) ? id : null;
    } catch {
      currentUserId.value = null;
    }
  })();
  fetchRoles();
  fetchUsers();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile);
});

const editDialogVisible = ref(false);
const editingUser = ref(null);
const selectedRoleIds = ref([]);
const saving = ref(false);

const currentUserId = ref(null);
const protectedRoleCodes = new Set(['superadmin', 'super_admin', 'super-admin']);
const isProtectedRole = (role) => protectedRoleCodes.has(String(role?.code || '').trim().toLowerCase());

const selectedUserIds = ref([]);
const resetPwdDialogVisible = ref(false);
const resetPwdForm = ref({ password: '' });
const currentResetUser = ref(null);
const resetting = ref(false);

const fetchRoles = async () => {
  try {
    const res = await axios.get('/api/v1/rbac/roles/with_users'); // Now returns counts
    if (res.data.code === 200) {
      roles.value = res.data.data || [];
    }
  } catch (e) {
    console.error(e);
  }
};

const fetchUsers = async () => {
  loading.value = true;
  try {
    const params = {
      page: currentPage.value,
      page_size: pageSize.value,
      q: searchQuery.value,
      role_id: filterRoleId.value
    };
    const res = await axios.get('/api/v1/rbac/roles/users_distribution', { params });
    if (res.data.code === 200) {
      tableData.value = res.data.data || [];
      total.value = res.data.meta?.total || 0;
    } else {
      ElMessage.error(res.data.message || '获取数据失败');
    }
  } catch (e) {
    ElMessage.error('获取数据失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = () => {
  currentPage.value = 1;
  fetchUsers();
};

const resetFilter = () => {
  searchQuery.value = '';
  filterRoleId.value = null;
  handleSearch();
};

const toggleRoleFilter = (roleId) => {
  if (filterRoleId.value === roleId) {
    filterRoleId.value = null;
  } else {
    filterRoleId.value = roleId;
  }
  handleSearch();
};

const handlePageChange = (val) => {
  currentPage.value = val;
  fetchUsers();
};

const handleSizeChange = (val) => {
  pageSize.value = val;
  currentPage.value = 1;
  fetchUsers();
};

const handleEditUserRoles = (user) => {
  editingUser.value = user;
  selectedRoleIds.value = (user.roles || []).map(r => r.id);
  editDialogVisible.value = true;
};

const handleSelectionChange = (selection) => {
  selectedUserIds.value = selection.map(item => item.id);
};

const handleBatchDelete = async () => {
  if (selectedUserIds.value.length === 0) return;
  try {
    await ElMessageBox.confirm(`确定要删除选中的 ${selectedUserIds.value.length} 个用户吗？此操作不可恢复。`, '批量删除确认', {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning'
    });
    
    const res = await axios.post('/api/v1/users/batch/delete', { user_ids: selectedUserIds.value });
    if (res.data.code === 200) {
      ElMessage.success('删除成功');
      fetchUsers();
      fetchRoles();
    } else {
      ElMessage.error(res.data.message || '删除失败');
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败');
  }
};

const handleResetPassword = (user) => {
  currentResetUser.value = user;
  resetPwdForm.value.password = '';
  resetPwdDialogVisible.value = true;
};

const submitResetPassword = async () => {
  if (!resetPwdForm.value.password) {
    ElMessage.warning('请输入新密码');
    return;
  }
  resetting.value = true;
  try {
    const res = await axios.put(`/api/v1/users/${currentResetUser.value.id}/password`, {
      password: resetPwdForm.value.password
    });
    if (res.data.code === 200) {
      ElMessage.success('密码重置成功');
      resetPwdDialogVisible.value = false;
    } else {
      ElMessage.error(res.data.message || '重置失败');
    }
  } catch (e) {
    ElMessage.error('重置失败');
  } finally {
    resetting.value = false;
  }
};

const handleDeleteUser = async (user) => {
  try {
    await ElMessageBox.confirm(`确定要删除用户 "${user.username}" 吗？`, '删除确认', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning'
    });
    const res = await axios.delete(`/api/v1/users/${user.id}`);
    if (res.data.code === 200) {
      ElMessage.success('删除成功');
      fetchUsers();
      fetchRoles();
    } else {
      ElMessage.error(res.data.message || '删除失败');
    }
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('删除失败');
  }
};

const saveUserRoles = async () => {
  if (!editingUser.value) return;
  saving.value = true;
  try {
    // We don't have a direct "set user roles" API yet, but we have "add users to role" and "remove user from role".
    // Or we can implement "set user roles" on backend?
    // Actually, usually RBAC has "set roles for user".
    // The existing APIs are role-centric: /roles/{id}/users (POST adds, DELETE removes).
    // This makes "set roles for user" tricky if we want to replace all roles.
    // We would need to:
    // 1. Get current roles (we have them).
    // 2. Diff.
    // 3. Call add/remove APIs.
    // OR: create a new API `PUT /api/v1/rbac/users/{user_id}/roles`
    
    // Let's quickly implement the diff logic here to avoid backend changes if possible, 
    // BUT backend change is cleaner.
    // Wait, I am allowed to make backend changes.
    // Let's implement `PUT /api/v1/rbac/users/{user_id}/roles` in backend in next step.
    // For now assume it exists or use a temporary workaround.
    // I will use a new API endpoint: PUT /api/v1/rbac/users/{id}/roles
    
    const res = await axios.put(`/api/v1/rbac/users/${editingUser.value.id}/roles`, {
      role_ids: selectedRoleIds.value
    });
    
    if (res.data.code === 200) {
      ElMessage.success('保存成功');
      editDialogVisible.value = false;
      fetchUsers(); // Refresh list
      fetchRoles(); // Refresh counts
    } else {
      ElMessage.error(res.data.message || '保存失败');
    }
  } catch (e) {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
};

onMounted(() => {
  // Removed duplicated onMounted logic, merging it above
});
</script>

<style scoped>
.rbac-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: #f5f7fa;
  color: #303133;
}

.rbac-header {
  height: 60px;
  background-color: #fff;
  border-bottom: 1px solid #dcdfe6;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
}

.info-icon {
  margin-left: 8px;
  color: #909399;
  cursor: help;
  font-size: 16px;
}

.rbac-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 16px;
  gap: 16px;
}

.role-summary-section {
  display: flex;
  gap: 12px;
  overflow-x: auto;
  padding-bottom: 4px;
  flex-shrink: 0;
}

.role-summary-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  min-width: 180px;
  border: 1px solid #ebeef5;
  cursor: pointer;
  display: flex;
  align-items: center;
  transition: all 0.2s;
  position: relative;
}

.role-summary-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}

.role-summary-card.active {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.role-card-icon {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background-color: #f0f2f5;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  color: #409eff;
}

.role-summary-card.active .role-card-icon {
  background-color: #fff;
}

.role-card-info {
  display: flex;
  flex-direction: column;
}

.role-name {
  font-weight: 600;
  font-size: 14px;
  margin-bottom: 4px;
}

.role-count {
  font-size: 12px;
  color: #909399;
}

.check-icon {
  position: absolute;
  top: 8px;
  right: 8px;
  color: #409eff;
}

.main-panel {
  flex: 1;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  box-shadow: 0 1px 4px rgba(0,0,0,0.02);
}

.filter-bar {
  display: flex;
  gap: 12px;
  margin-bottom: 16px;
}
.filter-input {
  width: 300px;
}
.filter-actions {
  display: flex;
  gap: 10px;
}

.table-container {
  flex: 1;
  overflow: hidden;
}

.pagination-container {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.role-checkbox {
  margin-right: 10px !important;
  margin-bottom: 10px !important;
  width: calc(33.33% - 10px);
}

.mr-1 { margin-right: 4px; }
.mb-1 { margin-bottom: 4px; }
.mr-2 { margin-right: 8px; }
.text-gray-400 { color: #9ca3af; }
.text-xs { font-size: 12px; }
.font-bold { font-weight: 600; }
.mb-4 { margin-bottom: 16px; }

/* Scrollbar */
.custom-scrollbar::-webkit-scrollbar {
  height: 6px;
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .rbac-container {
    height: auto;
    min-height: 100%;
  }
  
  .rbac-header {
    height: auto;
    flex-direction: column;
    align-items: flex-start;
    padding: 12px;
    gap: 8px;
  }
  
  .rbac-content {
    padding: 12px;
    gap: 12px;
  }
  
  .filter-bar {
    flex-direction: column;
    align-items: stretch;
  }
  
  .filter-input {
    width: 100% !important;
  }
  
  .filter-actions {
    display: flex;
    justify-content: space-between;
  }
  
  .filter-actions .el-button {
    flex: 1;
  }
  
  .pagination-container {
    justify-content: center;
  }
  
  .role-checkbox {
    width: 100% !important;
    margin-right: 0 !important;
  }
  
  .mobile-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  
  .user-card {
    border: 1px solid var(--el-border-color-light);
    border-radius: 8px;
    padding: 12px;
    background: #fff;
  }
  
  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 1px solid #ebeef5;
    padding-bottom: 8px;
    margin-bottom: 8px;
  }
  
  .user-main {
    display: flex;
    flex-direction: column;
  }
  
  .username {
    font-weight: 600;
    color: #303133;
  }
  
  .nickname {
    font-size: 12px;
    color: #909399;
  }
  
  .info-row {
    display: flex;
    margin-bottom: 6px;
    font-size: 13px;
  }
  
  .info-row.role-row {
    flex-direction: column;
    gap: 4px;
  }
  
  .label {
    color: #606266;
    margin-right: 8px;
    flex-shrink: 0;
  }
  
  .value {
    color: #303133;
    word-break: break-all;
  }
  
  .role-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 4px;
  }
  
  .card-actions {
    display: flex;
    justify-content: flex-end;
    margin-top: 8px;
    border-top: 1px solid #f0f2f5;
    padding-top: 8px;
  }
}
</style>
