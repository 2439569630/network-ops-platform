<template>
  <div class="repair-list-container">
    <el-card>
      <template #header>
        <div class="card-header">
          <div class="left">
            <span><el-icon><List /></el-icon> {{ headerTitle }}</span>
          </div>
          <div class="right">
            <!-- <el-button type="primary" icon="Plus" @click="$router.push('/user/repair/apply')">提交报修</el-button> -->
          </div>
        </div>
      </template>

      <!-- 运维人员视图切换 -->
      <div v-if="isYunwei" style="margin-bottom: 20px;">
        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
            <el-tab-pane label="派单列表" name="assigned"></el-tab-pane>
            <el-tab-pane label="我的报修" name="created"></el-tab-pane>
        </el-tabs>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <el-radio-group v-model="statusFilter" @change="fetchOrders">
          <el-radio-button label="">{{ isYunwei && activeTab === 'assigned' ? '待办任务' : '全部' }}</el-radio-button>
          <el-radio-button label="pending">待受理</el-radio-button>
          <el-radio-button label="processing">处理中</el-radio-button>
          <el-radio-button label="completed">已完成</el-radio-button>
          <el-radio-button label="cancelled">已取消</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 运维人员 - 派单列表 - 卡片视图 -->
      <div v-if="isYunwei && activeTab === 'assigned'" class="order-grid" v-loading="loading">
        <el-empty v-if="tableData.length === 0" description="暂无工单"></el-empty>
        <el-row :gutter="20">
            <el-col v-for="order in tableData" :key="order.id" :xs="24" :sm="12" :md="8" :lg="6" :xl="6">
                <el-card class="order-card" :class="{'priority-high': order.priority === 'emergency' || order.priority === 'high'}">
                    <template #header>
                        <div class="order-card-header">
                            <div class="header-top">
                                <span class="order-id">#{{ order.id }}</span>
                                <el-tag :type="getStatusType(order)" size="small" effect="dark">{{ getStatusLabel(order) }}</el-tag>
                            </div>
                            <div class="header-title" :title="order.title" @click="viewDetail(order.id)" style="cursor: pointer;">{{ order.title }}</div>
                        </div>
                    </template>
                    <div class="order-card-body" @click="viewDetail(order.id)" style="cursor: pointer;">
                         <div class="info-row">
                            <el-icon><Location /></el-icon>
                            <span class="text-truncate">{{ order.location_name || '未指定位置' }}</span>
                        </div>
                        <div class="info-row">
                             <el-icon><User /></el-icon>
                             <span>{{ order.submitter_name || '未知用户' }}</span>
                        </div>
                        <div class="info-row">
                            <el-icon><Clock /></el-icon>
                            <span>{{ formatDate(order.created_at) }}</span>
                        </div>
                         <div class="info-row priority-row">
                            <span class="label">优先级:</span>
                             <el-tag :type="getPriorityType(order.priority)" size="small" effect="plain" round>
                                {{ getPriorityLabel(order.priority) }}
                            </el-tag>
                        </div>
                    </div>
                    <div class="order-card-footer">
                        <el-button 
                            v-if="order.status === 'pending'" 
                            type="primary" 
                            size="small" 
                            class="action-btn"
                            @click="acceptOrder(order.id)"
                        >
                            {{ order.assignee_id === currentUserId ? '确认接单' : '快速抢单' }}
                        </el-button>
                         <el-button 
                            v-else-if="order.status === 'processing' && order.assignee_id === currentUserId" 
                            type="success" 
                            size="small" 
                            class="action-btn"
                            @click="viewDetail(order.id)"
                        >去处理</el-button>
                         <el-button 
                            v-else
                            plain 
                            size="small" 
                            class="action-btn"
                            @click="viewDetail(order.id)"
                        >查看详情</el-button>
                    </div>
                </el-card>
            </el-col>
        </el-row>
      </div>

      <!-- 列表 (非运维或运维的"我的报修"视图) -->
      <el-table 
        v-else
        :data="tableData" 
        style="width: 100%" 
        v-loading="loading"
        :header-cell-style="{ background: '#f5f7fa', color: '#606266' }"
      >
        <el-table-column prop="id" label="单号" width="90" align="center">
            <template #default="scope">
                <span style="font-family: monospace; color: #909399">#{{ scope.row.id }}</span>
            </template>
        </el-table-column>
        <el-table-column prop="title" label="标题" min-width="200" show-overflow-tooltip>
             <template #default="scope">
                <span style="font-weight: 500">{{ scope.row.title }}</span>
            </template>
        </el-table-column>
        <el-table-column prop="location_name" label="位置" width="180" show-overflow-tooltip>
            <template #default="scope">
                <div style="display: flex; align-items: center; gap: 4px; color: #606266;">
                    <el-icon><Location /></el-icon>
                    <span>{{ scope.row.location_name || '-' }}</span>
                </div>
            </template>
        </el-table-column>
        <el-table-column prop="priority" label="优先级" width="100" align="center">
          <template #default="scope">
            <el-tag :type="getPriorityType(scope.row.priority)" size="small" effect="plain" round>
              {{ getPriorityLabel(scope.row.priority) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="status" label="状态" width="100" align="center">
          <template #default="scope">
            <el-tag :type="getStatusType(scope.row)" size="small" effect="light" round>
              {{ getStatusLabel(scope.row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="created_at" label="提交时间" width="170" align="center">
            <template #default="scope">
                <span style="font-size: 13px; color: #909399">{{ formatDate(scope.row.created_at) }}</span>
            </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right" align="center">
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
import { List, Plus, Location, Search, User, Clock } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import axios from '@/axios/axios';
import { useRouter } from 'vue-router';
import { homeDataStore } from '@/components/home/home/data';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

const router = useRouter();
const store = homeDataStore();

const loading = ref(false);
const tableData = ref([]);
const page = ref(1);
const pageSize = ref(10);
const total = ref(0);
const statusFilter = ref('');
const roleCodes = ref([]);
const isSuper = ref(false);
const currentScope = ref('');
const activeTab = ref('assigned');

// 使用 store 中的权限判断
const isAdminOrManage = computed(() => {
    return store.isSuper || 
           (store.permissions && (store.permissions.includes('sys:repair:manage') || store.permissions.includes('sys:repair:list_all')));
});

const isYunwei = computed(() => {
    // 运维人员且非管理员
    return !isAdminOrManage.value && (roleCodes.value.includes('yunwei') || (store.permissions && store.permissions.includes('sys:repair:accept')));
});

const headerTitle = computed(() => {
    if (isAdminOrManage.value) return '工单列表';
    if (isYunwei.value) {
        return activeTab.value === 'assigned' ? '派单列表' : '我的报修';
    }
    return '我的工单';
});

const currentUserId = ref(null);

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
    // Check if input is object (row) or string
    let status = val;
    let assigneeId = null;
    
    if (typeof val === 'object' && val !== null) {
        status = val.status;
        assigneeId = val.assignee_id;
    }

    if (status === 'pending') {
        if (assigneeId) return '待接单'; // Assigned but not accepted
        return '待抢单'; // Unassigned
    }

    const map = { 
        pending: '待受理', 
        processing: '处理中', 
        completed: '已完成', 
        closed: '已关闭', 
        cancelled: '已取消',
        need_info: '需补充信息'
    };
    return map[status] || status;
};

const getStatusType = (val) => {
    let status = val;
    let assigneeId = null;

    if (typeof val === 'object' && val !== null) {
        status = val.status;
        assigneeId = val.assignee_id;
    }

    if (status === 'pending') {
        if (assigneeId) return 'warning'; // Orange for waiting accept
        return 'danger'; // Red for urgent pickup
    }

    const map = { 
        pending: 'info', 
        processing: 'primary', 
        completed: 'success', 
        closed: 'success', 
        cancelled: 'info',
        need_info: 'warning'
    };
    return map[status] || 'info';
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
                status: statusFilter.value || undefined,
                scope: currentScope.value || undefined
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

const handleTabChange = (tab) => {
    if (tab === 'assigned') {
        currentScope.value = 'assigned_to_me';
    } else if (tab === 'created') {
        currentScope.value = 'created_by_me';
    }
    page.value = 1;
    fetchOrders();
};

const viewDetail = (id) => {
    router.push(`/user/repair/detail/${id}`);
};

const canCancel = (row) => {
    // 允许待受理或处理中的工单取消
    return ['pending', 'processing'].includes(row?.status) && Number(row?.submitter_id) === Number(currentUserId.value);
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

const acceptOrder = async (id) => {
    try {
        await ElMessageBox.confirm('确定要接此工单吗?', '接单确认', {
            confirmButtonText: '确定接单',
            cancelButtonText: '取消',
            type: 'info',
        });
        const res = await axios.post(`/api/v1/repair-orders/${id}/accept`);
        if (res.data.code === 200) {
            ElMessage.success('接单成功');
            fetchOrders();
        }
    } catch (e) {
        if (e !== 'cancel') {
             ElMessage.error('接单失败');
        }
    }
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

            if (isYunwei.value) {
                currentScope.value = 'assigned_to_me';
                activeTab.value = 'assigned';
            } else if (isAdminOrManage.value) {
                currentScope.value = '';
            } else {
                currentScope.value = 'created_by_me';
            }
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

/* Card View Styles */
.order-grid {
    margin-bottom: 20px;
}
.order-card {
    margin-bottom: 20px;
    transition: all 0.3s;
    border-radius: 8px;
    border: 1px solid #ebeef5;
}
.order-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}
.order-card.priority-high {
    border-top: 3px solid #f56c6c;
}
.order-card-header {
    padding-bottom: 0;
}
.header-top {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.order-id {
    font-size: 12px;
    color: #909399;
    font-family: monospace;
}
.header-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.order-card-body {
    padding: 10px 0;
    font-size: 14px;
    color: #606266;
}
.info-row {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
    gap: 8px;
}
.info-row .el-icon {
    font-size: 16px;
    color: #909399;
}
.text-truncate {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}
.priority-row {
    margin-top: 12px;
    justify-content: space-between;
}
.priority-row .label {
    font-size: 12px;
    color: #909399;
}
.order-card-footer {
    border-top: 1px solid #ebeef5;
    padding-top: 12px;
    margin-top: 12px;
    display: flex;
    justify-content: flex-end;
}
.action-btn {
    width: 100%;
}
</style>
