<template>
  <div class="user-manage-page">
    <div class="page-header">
      <div class="header-main">
        <div class="header-title">
          <div class="title">用户管理</div>
          <!-- <div class="subtitle">支持按条件查询、创建、编辑、封禁与删除用户</div> -->
        </div>
        <div class="header-actions">
          <el-button type="primary" @click="openCreate">新建用户</el-button>
        </div>
      </div>
    </div>

    <el-card shadow="never" class="main-card">
      <div class="filter-bar">
        <el-input
          v-model="query.q"
          placeholder="搜索用户名/昵称/邮箱"
          clearable
          style="max-width: 320px"
          @keyup.enter="handleSearch"
          @clear="handleSearch"
        />
        <el-select v-model="query.is_approved" placeholder="账号状态" clearable style="width: 160px">
          <el-option :value="true" label="启用" />
          <el-option :value="false" label="封禁" />
        </el-select>
        <el-button type="primary" @click="handleSearch">查询</el-button>
        <el-button @click="resetFilter">重置</el-button>
      </div>

      <el-table
        :data="tableData"
        border
        stripe
        style="width: 100%"
        v-loading="loading"
        @selection-change="handleSelectionChange"
      >
        <el-table-column type="selection" width="55" />
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="username" label="用户名" min-width="140" />
        <el-table-column prop="nickname" label="昵称" min-width="140" />
        <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="100">
          <template #default="{ row }">
            <el-tag :type="row.is_approved ? 'success' : 'danger'">
              {{ row.is_approved ? '启用' : '封禁' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="320" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openDetail(row)">详情</el-button>
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-button link type="warning" @click="toggleStatus(row)">
              {{ row.is_approved ? '封禁' : '解封' }}
            </el-button>
            <el-button link type="primary" @click="openResetPwd(row)">重置密码</el-button>
            <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :total="total"
          :page-sizes="[20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="fetchUsers"
          @size-change="fetchUsers"
        />
      </div>
    </el-card>

    <el-dialog v-model="createVisible" title="新建用户" width="520px">
      <el-form :model="createForm" label-position="top">
        <el-form-item label="用户名">
          <el-input v-model="createForm.username" placeholder="请输入用户名" />
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="createForm.nickname" placeholder="可选" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="createForm.email" placeholder="可选" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="createForm.password" type="password" show-password placeholder="请输入初始密码" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitCreate">创建</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="editVisible" title="编辑用户" width="520px">
      <el-form :model="editForm" label-position="top">
        <el-form-item label="昵称">
          <el-input v-model="editForm.nickname" placeholder="可选" />
        </el-form-item>
        <el-form-item label="邮箱">
          <el-input v-model="editForm.email" placeholder="可选，留空将清空" />
        </el-form-item>
        <el-form-item label="邮件通知">
          <el-switch v-model="editForm.is_email_notify" />
        </el-form-item>
        <el-form-item label="账号状态">
          <el-switch v-model="editForm.is_approved" active-text="启用" inactive-text="封禁" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitEdit">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="detailVisible" title="用户详情" width="520px">
      <div v-if="detailData" class="detail">
        <div class="row"><span class="k">ID</span><span class="v">{{ detailData.id }}</span></div>
        <div class="row"><span class="k">用户名</span><span class="v">{{ detailData.username }}</span></div>
        <div class="row"><span class="k">昵称</span><span class="v">{{ detailData.nickname || '-' }}</span></div>
        <div class="row"><span class="k">邮箱</span><span class="v">{{ detailData.email || '-' }}</span></div>
        <div class="row"><span class="k">角色</span>
          <span class="v">
            <el-tag v-for="r in (detailData.roles || [])" :key="r.id" size="small" class="mr-1">{{ r.name }}</el-tag>
            <span v-if="!detailData.roles || detailData.roles.length === 0">-</span>
          </span>
        </div>
      </div>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="resetPwdVisible" title="重置密码" width="420px">
      <div v-if="resetPwdUser" class="mb-8">
        正在为用户 <b>{{ resetPwdUser.nickname || resetPwdUser.username }}</b> 重置密码
      </div>
      <el-form :model="resetPwdForm" label-position="top" @submit.prevent>
        <el-form-item label="新密码">
          <el-input v-model="resetPwdForm.password" type="password" show-password @keyup.enter="submitResetPwd" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="resetPwdVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="submitResetPwd">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';

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

const createVisible = ref(false);
const editVisible = ref(false);
const detailVisible = ref(false);
const resetPwdVisible = ref(false);

const createForm = reactive({
  username: '',
  nickname: '',
  email: '',
  password: ''
});

const editUserId = ref(null);
const editForm = reactive({
  nickname: '',
  email: '',
  is_email_notify: false,
  is_approved: true
});

const detailData = ref(null);
const resetPwdUser = ref(null);
const resetPwdForm = reactive({ password: '' });

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
      return;
    }
    ElMessage.error(res.data?.message || '获取用户列表失败');
  } catch (e) {
    ElMessage.error('获取用户列表失败');
  } finally {
    loading.value = false;
  }
};

const handleSearch = async () => {
  query.page = 1;
  await fetchUsers();
};

const resetFilter = async () => {
  query.q = '';
  query.is_approved = undefined;
  query.page = 1;
  query.page_size = 20;
  await fetchUsers();
};

const handleSelectionChange = (rows) => {
  selectedUserIds.value = Array.isArray(rows) ? rows.map(r => r.id) : [];
};

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
    const payload = {
      username: createForm.username,
      nickname: createForm.nickname || undefined,
      email: createForm.email || undefined,
      password: createForm.password
    };
    const res = await axios.post('/api/v1/users', payload);
    if (res.data?.code === 200) {
      ElMessage.success('创建成功');
      createVisible.value = false;
      await fetchUsers();
      return;
    }
    ElMessage.error(res.data?.message || '创建失败');
  } catch (e) {
    ElMessage.error('创建失败');
  } finally {
    saving.value = false;
  }
};

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
    const payload = {
      nickname: editForm.nickname,
      email: editForm.email,
      is_email_notify: editForm.is_email_notify,
      is_approved: editForm.is_approved
    };
    const res = await axios.put(`/api/v1/users/${editUserId.value}`, payload);
    if (res.data?.code === 200) {
      ElMessage.success('保存成功');
      editVisible.value = false;
      await fetchUsers();
      return;
    }
    ElMessage.error(res.data?.message || '保存失败');
  } catch (e) {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
};

const openDetail = async (row) => {
  detailVisible.value = true;
  detailData.value = null;
  try {
    const res = await axios.get(`/api/v1/users/${row.id}`);
    if (res.data?.code === 200) {
      detailData.value = res.data.data;
      return;
    }
    ElMessage.error(res.data?.message || '获取详情失败');
  } catch (e) {
    ElMessage.error('获取详情失败');
  }
};

const toggleStatus = async (row) => {
  try {
    await ElMessageBox.confirm(
      row.is_approved ? '确认封禁该用户？' : '确认解封该用户？',
      '提示',
      { type: 'warning' }
    );
  } catch {
    return;
  }
  saving.value = true;
  try {
    const res = await axios.post('/api/v1/users/status', { user_id: row.id, is_approved: !row.is_approved });
    if (res.data?.code === 200) {
      ElMessage.success('操作成功');
      await fetchUsers();
      return;
    }
    ElMessage.error(res.data?.message || '操作失败');
  } catch (e) {
    ElMessage.error('操作失败');
  } finally {
    saving.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm('确认删除该用户？此操作不可恢复。', '警告', { type: 'warning' });
  } catch {
    return;
  }
  saving.value = true;
  try {
    const res = await axios.delete(`/api/v1/users/${row.id}`);
    if (res.data?.code === 200) {
      ElMessage.success('删除成功');
      await fetchUsers();
      return;
    }
    ElMessage.error(res.data?.message || '删除失败');
  } catch (e) {
    ElMessage.error('删除失败');
  } finally {
    saving.value = false;
  }
};

const openResetPwd = (row) => {
  resetPwdUser.value = row;
  resetPwdForm.password = '';
  resetPwdVisible.value = true;
};

const submitResetPwd = async () => {
  if (!resetPwdUser.value?.id) return;
  if (!resetPwdForm.password) {
    ElMessage.warning('新密码不能为空');
    return;
  }
  saving.value = true;
  try {
    const res = await axios.put(`/api/v1/users/${resetPwdUser.value.id}/password`, { password: resetPwdForm.password });
    if (res.data?.code === 200) {
      ElMessage.success('重置成功');
      resetPwdVisible.value = false;
      return;
    }
    ElMessage.error(res.data?.message || '重置失败');
  } catch (e) {
    ElMessage.error('重置失败');
  } finally {
    saving.value = false;
  }
};

onMounted(fetchUsers);
</script>

<style scoped>
.user-manage-page {
  padding: 16px;
}
.page-header {
  margin-bottom: 12px;
}
.header-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
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
.pagination {
  display: flex;
  justify-content: flex-end;
  margin-top: 12px;
}
.detail .row {
  display: flex;
  gap: 10px;
  margin: 8px 0;
}
.detail .k {
  width: 80px;
  color: #6b7280;
}
.detail .v {
  flex: 1;
}
.mr-1 {
  margin-right: 6px;
}
.mb-8 {
  margin-bottom: 8px;
}
</style>
