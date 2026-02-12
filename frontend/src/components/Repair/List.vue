<template>
  <div class="repair-list-container" :class="{ 'is-mobile': isMobile }">
    <el-card class="list-card" :shadow="isMobile ? 'never' : 'always'">
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
      <div v-if="isYunwei" class="tab-container">
        <el-tabs v-model="activeTab" @tab-change="handleTabChange">
            <el-tab-pane label="派单列表" name="assigned"></el-tab-pane>
            <el-tab-pane label="我的报修" name="created"></el-tab-pane>
        </el-tabs>
      </div>

      <!-- 筛选栏 -->
      <div class="filter-bar">
        <div class="filter-scroll-wrapper" v-if="isMobile">
            <el-select v-model="statusFilter" @change="fetchOrders" placeholder="状态筛选" style="width: 140px">
                <el-option :label="isYunwei && activeTab === 'assigned' ? '待办任务' : '全部'" value="" />
                <el-option label="待受理" value="pending" />
                <el-option label="处理中" value="processing" />
                <el-option label="已完成" value="completed" />
                <el-option label="已取消" value="cancelled" />
            </el-select>
        </div>
        <el-radio-group v-else v-model="statusFilter" @change="fetchOrders">
          <el-radio-button label="">{{ isYunwei && activeTab === 'assigned' ? '待办任务' : '全部' }}</el-radio-button>
          <el-radio-button label="pending">待受理</el-radio-button>
          <el-radio-button label="processing">处理中</el-radio-button>
          <el-radio-button label="completed">已完成</el-radio-button>
          <el-radio-button label="cancelled">已取消</el-radio-button>
        </el-radio-group>
      </div>

      <!-- 卡片视图 (运维派单列表 OR 移动端所有列表) -->
      <div v-if="(isYunwei && activeTab === 'assigned') || isMobile" class="order-grid" v-loading="loading">
        <el-empty v-if="tableData.length === 0" description="暂无工单"></el-empty>
        <el-row :gutter="20">
            <el-col v-for="order in tableData" :key="order.id" :xs="24" :sm="12" :md="8" :lg="6" :xl="6">
                <el-card class="order-card" :class="{'priority-high': order.priority === 'emergency' || order.priority === 'high'}" shadow="hover" @click="viewDetail(order.id)">
                    <div class="order-card-content">
                        <div class="card-top-row">
                            <span class="order-id">#{{ order.id }}</span>
                            <el-tag :type="getStatusType(order)" size="small" effect="dark">{{ getStatusLabel(order) }}</el-tag>
                        </div>
                        <div class="card-title-row">{{ order.title }}</div>
                        
                        <div class="card-info-grid">
                            <div class="info-item">
                                <el-icon><Location /></el-icon>
                                <span class="text-truncate">{{ order.location_name || '未指定位置' }}</span>
                            </div>
                            <div class="info-item">
                                <el-icon><Clock /></el-icon>
                                <span>{{ formatDate(order.created_at) }}</span>
                            </div>
                             <div class="info-item" v-if="isYunwei">
                                 <el-icon><User /></el-icon>
                                 <span>{{ order.submitter_name || '未知用户' }}</span>
                            </div>
                        </div>

                        <div class="card-tags-row">
                             <el-tag :type="getPriorityType(order.priority)" size="small" effect="plain" round class="priority-tag">
                                {{ getPriorityLabel(order.priority) }}
                            </el-tag>
                        </div>
                    </div>
                    
                    <div class="order-card-footer" v-if="(isYunwei && activeTab === 'assigned') || canCancel(order) || canReview(order)">
                         <!-- 运维操作 -->
                        <template v-if="isYunwei && activeTab === 'assigned'">
                            <el-button 
                                v-if="order.status === 'pending'" 
                                type="primary" 
                                size="small" 
                                class="action-btn"
                                @click.stop="acceptOrder(order.id)"
                            >
                                {{ order.assignee_id === currentUserId ? '确认接单' : '快速接单' }}
                            </el-button>
                             <el-button 
                                v-else-if="order.status === 'processing' && order.assignee_id === currentUserId" 
                                type="success" 
                                size="small" 
                                class="action-btn"
                                @click.stop="viewDetail(order.id)"
                            >去处理</el-button>
                        </template>

                        <!-- 用户操作 -->
                         <template v-else>
                            <el-button 
                                v-if="canCancel(order)" 
                                type="danger" 
                                plain
                                size="small" 
                                class="action-btn"
                                @click.stop="cancelOrder(order.id)"
                            >取消</el-button>
                            <el-button 
                                v-if="canReview(order)" 
                                type="success" 
                                plain
                                size="small" 
                                class="action-btn"
                                @click.stop="reviewOrder(order.id)"
                            >评价</el-button>
                         </template>
                    </div>
                </el-card>
            </el-col>
        </el-row>
      </div>

      <!-- PC端表格 (非运维或运维的"我的报修"视图) -->
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
          :layout="isMobile ? 'prev, pager, next' : 'total, sizes, prev, pager, next, jumper'"
          :total="total"
          :small="isMobile"
          @size-change="fetchOrders"
          @current-change="fetchOrders"
        />
      </div>
    </el-card>

    <!-- 评价对话框 -->
    <el-dialog v-model="reviewDialogVisible" title="服务评价" :width="isMobile ? '90%' : '500px'">
        <el-form :model="reviewForm" label-width="100px" label-position="top">
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
import { ref, onMounted, onBeforeUnmount, reactive, computed } from 'vue';
import { List, Plus, Location, Search, User, Clock } from '@element-plus/icons-vue';
import { ElMessage, ElMessageBox } from 'element-plus';
import axios from '@/axios/axios';
import { useRouter } from 'vue-router';
import { homeDataStore } from '@/components/home/home/data';

const router = useRouter();
const store = homeDataStore();

const isMobile = ref(window.innerWidth < 768)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }

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
        return '待接单'; // Unassigned
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

onMounted(async () => {
    store.syncAuthFromToken();
    try {
        const session = await store.ensureSession();
        if (session) {
            const roles = Array.isArray(store.roleCodes) ? store.roleCodes.map(r => String(r).toLowerCase()) : [];
            roleCodes.value = roles;
            isSuper.value = Boolean(store.isSuper);
            currentUserId.value = session?.id ?? null;
        }
    } catch {}

    if (isYunwei.value) {
        currentScope.value = 'assigned_to_me';
        activeTab.value = 'assigned';
    } else if (isAdminOrManage.value) {
        currentScope.value = '';
    } else {
        currentScope.value = 'created_by_me';
    }

    fetchOrders();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped>
.repair-list-container {
    height: 100%;
    display: flex;
    flex-direction: column;
}

.repair-list-container.is-mobile {
    padding: 0;
}

.list-card {
    border: none;
    box-shadow: none;
}

.repair-list-container:not(.is-mobile) .list-card {
    margin: 20px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.filter-bar {
    margin-bottom: 20px;
}

.filter-scroll-wrapper {
    width: 100%;
    overflow-x: auto;
    padding-bottom: 4px;
}

.pagination-container {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
}

.is-mobile .pagination-container {
    justify-content: center;
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
    cursor: pointer;
    position: relative;
    overflow: hidden;
}

/* Mobile specific card tweaks */
.is-mobile .order-card {
    margin-bottom: 12px;
    border: none;
    border-bottom: 1px solid #f0f0f0;
    border-radius: 0;
    box-shadow: none !important;
    padding-bottom: 12px;
}

.is-mobile .order-card:last-child {
    border-bottom: none;
}

.is-mobile .el-card__body {
    padding: 12px;
}

.order-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.is-mobile .order-card:hover {
    transform: none;
    box-shadow: none;
    background-color: #fafafa;
}

.order-card.priority-high {
    border-left: 4px solid #f56c6c;
}

.is-mobile .order-card.priority-high {
    border-left: 4px solid #f56c6c;
}

.order-card-content {
    padding: 12px;
}

.card-top-row {
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

.card-title-row {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    margin-bottom: 12px;
    line-height: 1.4;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
}

.card-info-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 12px;
    margin-bottom: 12px;
}

.info-item {
    display: flex;
    align-items: center;
    gap: 4px;
    font-size: 13px;
    color: #606266;
}

.info-item .el-icon {
    color: #909399;
}

.text-truncate {
    max-width: 150px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.card-tags-row {
    display: flex;
    justify-content: flex-end;
}

.order-card-footer {
    border-top: 1px solid #ebeef5;
    padding: 10px 12px 0 12px;
    margin-bottom: 12px; /* padding-bottom of card body is usually 20px */
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}

.action-btn {
    min-width: 80px;
}
</style>
