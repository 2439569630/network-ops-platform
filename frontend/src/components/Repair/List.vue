<template>
  <div class="repair-list-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="left">
            <span><el-icon><List /></el-icon> {{ headerTitle }}</span>
          </div>
          <div class="right">
            <el-button type="primary" icon="Plus" @click="$router.push('/user/repair/apply')">提交报修</el-button>
          </div>
        </div>
      </template>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-radio-group v-model="statusFilter" @change="fetchOrders">
          <el-radio-button label="">全部</el-radio-button>
          <el-radio-button label="pending">待受理</el-radio-button>
          <el-radio-button label="processing">处理中</el-radio-button>
          <el-radio-button label="completed">已完成</el-radio-button>
          <el-radio-button label="cancelled">已取消</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 列表 -->
      <el-table :data="tableData" style="width: 100%" v-loading="loading">
        <el-table-column prop="id" label="单号" width="80" />
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip />
        <el-table-column prop="device_name" label="关联设备" width="150">
            <template #default="scope">
                {{ scope.row.device_name || '-' }}
            </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="100">
          <template #default="scope">
            <el-tag :type="getPriorityType(scope.row.priority)" size="small">
              {{ getPriorityLabel(scope.row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row.status)" size="small" effect="dark">
              {{ getStatusLabel(scope.row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="提交时间" width="180">
            <template #default="scope">
                {{ formatDate(scope.row.created_at) }}
            </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="scope">
            <el-button type="primary" link size="small" @click="viewDetail(scope.row.id)">详情</el-button>
            <el-button 
                v-if="canCancel(scope.row)" 
                type="danger" 
                link 
                size="small" 
                @click="cancelOrder(scope.row.id)"
            >取消</el-button>
            <el-button 
                v-if="canReview(scope.row)" 
                type="success" 
                link 
                size="small" 
                @click="reviewOrder(scope.row.id)"
            >评价</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-container">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next, jumper"
          :total="total"
          @size-change="fetchOrders"
          @current-change="fetchOrders"
        />
      </div>
    </el-card>

    <!-- 评价对话框 -->
    <el-dialog v-model="reviewDialogVisible" title="服务评价" width="500px">
        <el-form :model="reviewForm" label-width="100px">
            <el-form-item label="总体评分">
                <el-rate v-model="reviewForm.rating" show-text />
            </el-form-item>
            <el-form-item label="响应速度">
                <el-rate v-model="reviewForm.response_time_rating" />
            </el-form-item>
            <el-form-item label="服务质量">
                <el-rate v-model="reviewForm.service_quality_rating" />
            </el-form-item>
            <el-form-item label="评价内容">
                <el-input v-model="reviewForm.comment" type="textarea" />
            </el-form-item>
        </el-form>
        <template #footer>
            <span class="dialog-footer">
                <el-button @click="reviewDialogVisible = false">取消</el-button>
                <el-button type="primary" @click="submitReview">提交评价</el-button>
            </span>
        </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, reactive, computed } from 'vue';
import { List, Plus } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import axios from '@/axios/axios';
import { useRouter } from 'vue-router';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

const router = useRouter();
const loading = ref(false);
const tableData = ref([]);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const statusFilter = ref('');
const roleCodes = ref([]);
const isSuper = ref(false);
const currentUserId = ref(null);

const headerTitle = computed(() => {
    if (isSuper.value) return '工单列表';
    if (roleCodes.value.includes('yunwei')) return '待处理工单';
    return '我的工单';
});

// 评价相关
const reviewDialogVisible = ref(false);
const currentReviewOrderId = ref(null);
const reviewForm = reactive({
    rating: 5,
    response_time_rating: 5,
    service_quality_rating: 5,
    comment: ''
});

const getPriorityLabel = (val) => {
    const map = { low: '低', medium: '中', high: '高', emergency: '紧急' };
    return map[val] || val;
};
const getPriorityType = (val) => {
    const map = { low: 'info', medium: '', high: 'warning', emergency: 'danger' };
    return map[val] || '';
};
const getStatusLabel = (val) => {
    const map = { 
        pending: '待受理', 
        processing: '处理中', 
        completed: '已完成', 
        closed: '已关闭', 
        cancelled: '已取消',
        need_info: '需补充信息'
    };
    return map[val] || val;
};
const getStatusType = (val) => {
    const map = { 
        pending: 'info', 
        processing: 'primary', 
        completed: 'success', 
        closed: 'success', 
        cancelled: 'info',
        need_info: 'warning'
    };
    return map[val] || 'info';
};

const formatDate = (str) => {
    if (!str) return '-';
    return new Date(str).toLocaleString();
};

const fetchOrders = async () => {
    loading.value = true;
    try {
        const res = await axios.get('/api/v1/repair-orders/', {
            params: {
                page: page.value,
                page_size: pageSize.value,
                status: statusFilter.value || undefined
            }
        });
        if (res.data.code === 200) {
            tableData.value = res.data.data.items;
            total.value = res.data.data.total;
        }
    } catch (error) {
        ElMessage.error('获取列表失败');
    } finally {
        loading.value = false;
    }
};

const viewDetail = (id) => {
    router.push(`/user/repair/detail/${id}`);
};

const canCancel = (row) => {
    return row?.status === 'pending' && Number(row?.submitter_id) === Number(currentUserId.value);
};

const canReview = (row) => {
    return row?.status === 'completed' && Number(row?.submitter_id) === Number(currentUserId.value);
};

const cancelOrder = async (id) => {
    try {
        await ElMessageBox.prompt('请输入取消原因', '取消工单', {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
        }).then(async ({ value }) => {
            const res = await axios.post(`/api/v1/repair-orders/${id}/cancel`, { reason: value || '用户主动取消' });
            if (res.data.code === 200) {
                ElMessage.success('已取消');
                fetchOrders();
            }
        });
    } catch (e) {
        // cancel or error
    }
};

const reviewOrder = (id) => {
    currentReviewOrderId.value = id;
    reviewForm.rating = 5;
    reviewForm.comment = '';
    reviewDialogVisible.value = true;
};

const submitReview = async () => {
    try {
        const res = await axios.post(`/api/v1/repair-orders/${currentReviewOrderId.value}/review`, reviewForm);
        if (res.data.code === 200) {
            ElMessage.success('评价成功');
            reviewDialogVisible.value = false;
            fetchOrders();
        }
    } catch (error) {
        ElMessage.error('评价失败');
    }
};

onMounted(() => {
    const token = Cookies.get('token');
    if (token) {
        try {
            const decoded = jwtDecode(token);
            const roles = Array.isArray(decoded.roles) ? decoded.roles.map(r => String(r).toLowerCase()) : [];
            roleCodes.value = roles;
            isSuper.value = Boolean(decoded.is_super) || roles.includes('admin') || roles.includes('superadmin') || roles.includes('super_admin') || roles.includes('super-admin');
            currentUserId.value = decoded.id;
        } catch (e) {
            // ignore
        }
    }
    fetchOrders();
});
</script>

<style scoped>
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.filter-bar {
    margin-bottom: 20px;
}
.pagination-container {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
}
</style>
