<template>
  <div class="permission-management">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>权限管理</span>
          <el-button type="primary" @click="openCreate">新建权限</el-button>
        </div>
      </template>

      <el-table :data="tableData" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="ID" width="80" />
        <el-table-column prop="name" label="名称" width="200" />
        <el-table-column prop="code" label="编码" min-width="220" show-overflow-tooltip />
        <el-table-column prop="description" label="描述" min-width="240" show-overflow-tooltip />
        <el-table-column label="操作" width="180" fixed="right">
          <template #default="scope">
            <el-button type="primary" link @click="openEdit(scope.row)">编辑</el-button>
            <el-button type="danger" link @click="handleDelete(scope.row)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px">
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-form-item label="编码">
          <el-input v-model="form.code" placeholder="例如：sys:user:view" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="3" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave" :loading="saving">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { onMounted, ref, reactive, computed } from 'vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';

const loading = ref(false);
const saving = ref(false);
const tableData = ref([]);
const roleUsersData = ref([]);

const dialogVisible = ref(false);
const editingId = ref(null);
const dialogTitle = computed(() => (editingId.value ? '编辑权限' : '新建权限'));

const form = reactive({
  name: '',
  code: '',
  description: ''
});

const resetForm = () => {
  form.name = '';
  form.code = '';
  form.description = '';
  editingId.value = null;
};

const fetchList = async () => {
  loading.value = true;
  try {
    const res = await axios.get('/api/v1/rbac/permissions');
    if (res.data.code === 200) {
      tableData.value = res.data.data || [];
    } else {
      ElMessage.error(res.data.message || '获取权限列表失败');
    }
  } catch (e) {
    ElMessage.error('获取权限列表失败');
  } finally {
    loading.value = false;
  }
};

const openCreate = () => {
  resetForm();
  dialogVisible.value = true;
};

const openEdit = (row) => {
  editingId.value = row.id;
  form.name = row.name || '';
  form.code = row.code || '';
  form.description = row.description || '';
  dialogVisible.value = true;
};

const handleSave = async () => {
  if (!form.name || !form.code) {
    ElMessage.warning('名称和编码不能为空');
    return;
  }
  saving.value = true;
  try {
    if (editingId.value) {
      const res = await axios.put(`/api/v1/rbac/permissions/${editingId.value}`, form);
      if (res.data.code === 200) {
        ElMessage.success('保存成功');
        dialogVisible.value = false;
        await fetchList();
      } else {
        ElMessage.error(res.data.message || '保存失败');
      }
    } else {
      const res = await axios.post('/api/v1/rbac/permissions', form);
      if (res.data.code === 200) {
        ElMessage.success('创建成功');
        dialogVisible.value = false;
        await fetchList();
      } else {
        ElMessage.error(res.data.message || '创建失败');
      }
    }
  } catch (e) {
    ElMessage.error('保存失败');
  } finally {
    saving.value = false;
  }
};

const handleDelete = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除权限「${row.name}」吗？`, '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    });
    const res = await axios.delete(`/api/v1/rbac/permissions/${row.id}`);
    if (res.data.code === 200) {
      ElMessage.success('删除成功');
      await fetchList();
    } else {
      ElMessage.error(res.data.message || '删除失败');
    }
  } catch (e) {}
};

onMounted(() => {
  fetchList();
});
</script>

<style scoped>
.permission-management {
  padding: 10px;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>

