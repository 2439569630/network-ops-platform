<template>
  <div class="repair-detail-container">
    <el-card v-loading="loading">
      <template #header>
        <div class="card-header">
          <div class="left">
            <el-button icon="ArrowLeft" @click="$router.back()">返回</el-button>
            <span class="title">工单详情 #{{ order?.id }}</span>
            <el-tag v-if="order" :type="getStatusType(order.status)" class="status-tag">
                {{ getStatusLabel(order.status) }}
            </el-tag>
          </div>
          <div class="right">
             <!-- 管理员操作区 -->
             <div v-if="isAdmin && order?.status === 'pending'">
                 <el-button type="primary" @click="dialogAssignVisible = true">派单</el-button>
             </div>
             <!-- 维修人员操作区 -->
             <div v-if="isMaintenance && order?.status === 'pending'">
                 <el-button type="primary" @click="handleAccept">接单</el-button>
             </div>
             <div v-if="(isMaintenance || isAdmin) && order?.status === 'processing'">
                 <el-button type="success" @click="handleComplete">完成工单</el-button>
             </div>
          </div>
        </div>
      </template>

      <div v-if="order" class="detail-content">
        <el-descriptions border :column="2">
            <el-descriptions-item label="标题" :span="2">{{ order.title }}</el-descriptions-item>
            <el-descriptions-item label="报修人">{{ order.submitter_name }}</el-descriptions-item>
            <el-descriptions-item label="提交时间">{{ formatDate(order.created_at) }}</el-descriptions-item>
            <el-descriptions-item label="关联设备">{{ order.device_name || '无' }}</el-descriptions-item>
            <el-descriptions-item label="优先级">
                <el-tag :type="getPriorityType(order.priority)">{{ getPriorityLabel(order.priority) }}</el-tag>
            </el-descriptions-item>
            <el-descriptions-item label="当前处理人">{{ order.assignee_name || '未指派' }}</el-descriptions-item>
            <el-descriptions-item label="问题描述" :span="2">
                <div class="description-box">{{ order.description }}</div>
            </el-descriptions-item>
        </el-descriptions>

        <!-- 评价信息 -->
        <div v-if="order.review" class="section review-section">
            <h3>用户评价</h3>
            <el-rate v-model="order.review.rating" disabled show-score text-color="#ff9900" />
            <div class="review-text">{{ order.review.comment }}</div>
        </div>

        <!-- 流转日志 -->
        <div class="section log-section">
            <h3>处理记录</h3>
            <el-timeline>
                <el-timeline-item
                    v-for="(log, index) in order.logs"
                    :key="index"
                    :timestamp="formatDate(log.created_at)"
                    :type="getLogType(log.action)"
                >
                    <h4>{{ getActionLabel(log.action) }} - {{ log.operator_name || '系统' }}</h4>
                    <p v-if="log.remark">{{ log.remark }}</p>
                    <p v-if="log.from_status !== log.to_status" class="status-change">
                        状态变更: {{ getStatusLabel(log.from_status) }} -> {{ getStatusLabel(log.to_status) }}
                    </p>
                </el-timeline-item>
            </el-timeline>
        </div>
      </div>
    </el-card>

    <!-- 派单弹窗 -->
    <el-dialog v-model="dialogAssignVisible" title="派发工单" width="400px">
        <el-form>
            <el-form-item label="选择维修人员">
                <el-select v-model="assignForm.assignee_id" placeholder="请选择">
                    <el-option 
                        v-for="user in maintenanceUsers" 
                        :key="user.id" 
                        :label="user.username" 
                        :value="user.id" 
                    />
                </el-select>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="dialogAssignVisible = false">取消</el-button>
            <el-button type="primary" @click="handleAssign">确定</el-button>
        </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue';
import { useRoute } from 'vue-router';
import { ArrowLeft } from '@element-plus/icons-vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';

const route = useRoute();
const orderId = route.params.id;
const order = ref(null);
const loading = ref(false);
const currentUserRole = ref(2); // Default user

// 派单相关
const dialogAssignVisible = ref(false);
const maintenanceUsers = ref([]); // 维修人员列表
const assignForm = ref({ assignee_id: null });

const isAdmin = computed(() => currentUserRole.value === 0);
const isMaintenance = computed(() => currentUserRole.value === 1);

// Helper functions (Same as List.vue, ideally move to utils)
const getPriorityLabel = (val) => ({ low: '低', medium: '中', high: '高', emergency: '紧急' }[val] || val);
const getPriorityType = (val) => ({ low: 'info', medium: '', high: 'warning', emergency: 'danger' }[val] || '');
const getStatusLabel = (val) => ({ 
    pending: '待受理', processing: '处理中', completed: '已完成', closed: '已关闭', cancelled: '已取消' 
}[val] || val);
const getStatusType = (val) => ({ 
    pending: 'info', processing: 'primary', completed: 'success', closed: 'success', cancelled: 'info' 
}[val] || 'info');
const formatDate = (str) => str ? new Date(str).toLocaleString() : '-';

const getActionLabel = (val) => ({
    create: '创建工单', assign: '指派工单', accept: '接单', complete: '完成工单', 
    cancel: '取消工单', review: '评价', update_status: '更新状态', remark: '添加备注'
}[val] || val);

const getLogType = (action) => {
    if (action === 'create') return 'primary';
    if (action === 'complete') return 'success';
    if (action === 'cancel') return 'danger';
    return '';
};

const fetchDetail = async () => {
    loading.value = true;
    try {
        const res = await axios.get(`/api/v1/repair-orders/${orderId}`);
        if (res.data.code === 200) {
            order.value = res.data.data;
        } else {
            ElMessage.error(res.data.message);
        }
    } catch (error) {
        ElMessage.error('获取详情失败');
    } finally {
        loading.value = false;
    }
};

const fetchMaintenanceUsers = async () => {
    // 假设有一个接口获取维修人员列表，或者获取所有用户后过滤
    // 这里简化处理
    try {
        const res = await axios.get('/api/v1/users/roleList'); // 复用用户列表
        if (res.data.code === 200) {
            // 过滤 role = 1 (维修)
            maintenanceUsers.value = res.data.data.filter(u => u.permission_level === 1);
        }
    } catch (e) {}
};

const handleAssign = async () => {
    if (!assignForm.value.assignee_id) return;
    try {
        const res = await axios.post(`/api/v1/repair-orders/${orderId}/assign`, { assignee_id: assignForm.value.assignee_id });
        if (res.data.code === 200) {
            ElMessage.success('派单成功');
            dialogAssignVisible.value = false;
            fetchDetail();
        }
    } catch (e) {
        ElMessage.error('操作失败');
    }
};

const handleAccept = async () => {
    try {
        const res = await axios.post(`/api/v1/repair-orders/${orderId}/accept`);
        if (res.data.code === 200) {
            ElMessage.success('接单成功');
            fetchDetail();
        }
    } catch (e) {
        ElMessage.error('操作失败');
    }
};

const handleComplete = async () => {
    try {
        await ElMessageBox.prompt('请输入处理备注（可选）', '完成工单', {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
        }).then(async ({ value }) => {
            const res = await axios.post(`/api/v1/repair-orders/${orderId}/complete`, { remark: value });
            if (res.data.code === 200) {
                ElMessage.success('工单已完成');
                fetchDetail();
            }
        });
    } catch (e) {
        // ignore
    }
};

onMounted(() => {
    const token = Cookies.get('token');
    if (token) {
        try {
            const decoded = jwtDecode(token);
            currentUserRole.value = decoded.permission_level;
        } catch (e) {}
    }
    fetchDetail();
    if (currentUserRole.value === 0) {
        fetchMaintenanceUsers();
    }
});
</script>

<style scoped>
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.left {
    display: flex;
    align-items: center;
    gap: 10px;
}
.title {
    font-weight: bold;
    font-size: 16px;
}
.detail-content {
    margin-top: 20px;
}
.description-box {
    white-space: pre-wrap;
    line-height: 1.5;
}
.section {
    margin-top: 30px;
}
.section h3 {
    margin-bottom: 15px;
    border-left: 4px solid #409eff;
    padding-left: 10px;
}
.review-section {
    background: #fdf6ec;
    padding: 15px;
    border-radius: 4px;
}
.status-change {
    font-size: 12px;
    color: #909399;
}
</style>