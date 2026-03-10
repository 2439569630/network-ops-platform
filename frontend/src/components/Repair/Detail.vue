<template>
  <div class="repair-detail-wrapper" :class="{ 'is-mobile': isMobile }">
    <div class="page-header">
        <el-page-header @back="goBack" :title="isMobile ? '' : '返回列表'" :icon="ArrowLeft">
            <template #content>
                <div class="header-content">
                    <span class="header-title">工单详情 #{{ order?.id }}</span>
                    <el-tag v-if="order" :type="getStatusType(order)" effect="dark" round size="small">
                        {{ getStatusLabel(order) }}
                    </el-tag>
                </div>
            </template>
            <template #extra>
                <div class="header-actions">
                    <el-button
                        v-if="!isMobile"
                        class="hidden-xs-only"
                        style="background-color: #409EFF; border-color: #409EFF; color: #fff;"
                        @mouseover="this.style.backgroundColor='#66b1ff'; this.style.borderColor='#66b1ff'"
                        @mouseout="this.style.backgroundColor='#409EFF'; this.style.borderColor='#409EFF'"
                        @click="goBack"
                    >返回列表</el-button>
                     <!-- 管理员特殊权限：修改状态 -->
                    <el-button 
                        v-if="canManageRepair" 
                        type="warning" 
                        plain 
                        icon="Edit"
                        @click="dialogStatusVisible = true"
                        :size="isMobile ? 'small' : 'default'"
                        class="status-btn-mobile"
                    >{{ isMobile ? '改状态' : '修改状态' }}</el-button>

                    <el-button
                        v-if="canEditOrder"
                        type="primary"
                        plain
                        @click="openEditDialog"
                        :size="isMobile ? 'small' : 'default'"
                    >{{ isMobile ? '编辑' : '编辑工单' }}</el-button>

                    <el-button
                        v-if="canDeleteOrder"
                        type="danger"
                        plain
                        @click="handleDeleteOrder"
                        :size="isMobile ? 'small' : 'default'"
                    >{{ isMobile ? '删除' : '删除工单' }}</el-button>
                    
                    <el-button icon="Refresh" circle @click="fetchDetail" :size="isMobile ? 'small' : 'default'" />
                </div>
            </template>
        </el-page-header>
    </div>

    <div v-loading="loading" class="main-content">
        <el-row :gutter="20">
            <!-- 左侧主要内容 -->
            <el-col :xs="24" :lg="16">
                <!-- 流程进度 -->
                <el-card class="step-card" :shadow="isMobile ? 'never' : 'hover'">
                    <el-steps :active="currentStep" finish-status="success" :align-center="!isMobile" :direction="isMobile ? 'vertical' : 'horizontal'">
                        <el-step title="提交" :description="formatDate(order?.created_at)" />
                        <el-step title="待接单" />
                        <el-step title="维修中" />
                        <el-step title="已完成" />
                        <el-step title="已评价" />
                    </el-steps>
                </el-card>

                <!-- 故障详情 -->
                <el-card class="detail-card" :shadow="isMobile ? 'never' : 'hover'">
                    <template #header>
                        <div class="card-title">
                            <el-icon><Document /></el-icon> 故障详情
                        </div>
                    </template>
                    
                    <div class="info-grid">
                        <div class="info-item full-width">
                            <label>故障标题</label>
                            <div class="content title-text">{{ order?.title }}</div>
                        </div>
                         <div class="info-item full-width">
                            <label>问题描述</label>
                            <div class="content description-box">{{ order?.description }}</div>
                        </div>
                        <div v-if="order?.images?.length" class="info-item full-width">
                            <label>报修图片</label>
                            <div class="content order-images">
                                <el-image
                                    v-for="(img, idx) in order.images"
                                    :key="idx"
                                    :src="img"
                                    :preview-src-list="order.images"
                                    fit="cover"
                                    class="log-image"
                                ></el-image>
                            </div>
                        </div>
                        <div class="info-item">
                            <label>报修位置</label>
                            <div class="content"><el-icon><Location /></el-icon> {{ fullLocationPath || order?.location_name || '未指定' }}</div>
                        </div>
                        <div class="info-item">
                            <label>优先级</label>
                            <div class="content">
                                <el-tag :type="getPriorityType(order?.priority)" size="small" effect="plain">
                                    {{ getPriorityLabel(order?.priority) }}
                                </el-tag>
                            </div>
                        </div>
                    </div>
                </el-card>

                <!-- 关联设备 -->
                <el-card v-if="canViewRelatedDevices && (order?.location_id || order?.location_name)" class="device-card" :shadow="isMobile ? 'never' : 'hover'">
                    <template #header>
                        <div class="card-title">
                            <el-icon><Monitor /></el-icon> 关联设备
                            <span v-if="fullLocationPath || order?.location_name" style="font-size: 12px; color: #909399; font-weight: normal; margin-left: 8px;">
                                <!-- ({{ fullLocationPath || order.location_name }}) -->
                            </span>
                        </div>
                    </template>
                    
                    <div v-loading="loadingDevices">
                        <el-alert
                            v-if="deviceFetchForbidden"
                            type="warning"
                            title="无权限查看关联设备"
                            :closable="false"
                            style="margin-bottom: 12px;"
                        />
                        <el-alert
                            v-else-if="deviceFetchError"
                            type="error"
                            :title="deviceFetchError"
                            :closable="false"
                            style="margin-bottom: 12px;"
                        />
                        <el-table 
                            v-else-if="relatedDevices.length > 0" 
                            :data="relatedDevices" 
                            style="width: 100%" 
                            size="small"
                        >
                            <el-table-column prop="device_name" label="设备名称" min-width="120" show-overflow-tooltip />
                            <el-table-column prop="ipv4" label="IP地址" width="130" />
                            <el-table-column label="状态" width="100">
                                <template #default="{ row }">
                                    <el-tag :type="getDeviceStatusTagType(row)" size="small">
                                        {{ getDeviceStatusText(row, nowTick) }}
                                    </el-tag>
                                </template>
                            </el-table-column>
                            <el-table-column label="操作" width="80" fixed="right">
                                <template #default="{ row }">
                                    <el-button 
                                        v-if="canSsh && isSshEnabled(row)" 
                                        type="success" 
                                        link 
                                        size="small" 
                                        @click="handleSSH(row)"
                                    >
                                        <el-icon><Connection /></el-icon> SSH
                                    </el-button>
                                </template>
                            </el-table-column>
                        </el-table>
                        
                        <el-empty v-else description="该位置下暂无关联设备" :image-size="60">
                             <template #description>
                                <p>该位置 ({{ fullLocationPath || order?.location_name || '未知' }}) 下暂无绑定设备</p>
                            </template>
                        </el-empty>
                    </div>
                </el-card>

                <!-- 工作记录 (新增) -->
                <el-card class="work-log-card" :shadow="isMobile ? 'never' : 'hover'">
                    <template #header>
                        <div class="card-title">
                            <el-icon><Tools /></el-icon> 维修工作记录
                             <el-button 
                                v-if="isMaintenance && order?.status === 'processing'" 
                                type="primary" 
                                size="small" 
                                link 
                                @click="dialogWorkLogVisible = true"
                                style="margin-left: auto;"
                            >添加记录</el-button>
                        </div>
                    </template>
                    
                    <div v-if="order?.work_logs?.length" class="work-logs">
                        <div v-for="log in order.work_logs" :key="log.id" class="work-log-item">
                            <div class="work-log-header">
                                <span class="operator">{{ log.operator_name }}</span>
                                <span class="time">{{ formatDate(log.created_at) }}</span>
                            </div>
                            <div class="work-log-content">{{ log.content }}</div>
                            <div v-if="log.images && log.images.length" class="work-log-images">
                                <!-- Placeholder for images -->
                                <el-image 
                                    v-for="(img, idx) in log.images" 
                                    :key="idx" 
                                    :src="img" 
                                    :preview-src-list="log.images"
                                    fit="cover"
                                    class="log-image"
                                ></el-image>
                            </div>
                        </div>
                    </div>
                    <el-empty v-else description="暂无工作记录" :image-size="60"></el-empty>
                </el-card>

                <!-- 处理记录 -->
                <el-card class="log-card" :shadow="isMobile ? 'never' : 'hover'">
                    <template #header>
                        <div class="card-title">
                            <el-icon><Timer /></el-icon> 处理记录
                        </div>
                    </template>
                    <el-timeline>
                        <el-timeline-item
                            v-for="(log, index) in processedLogs"
                            :key="index"
                            :timestamp="formatDate(log.created_at)"
                            :type="getLogType(log.action)"
                            :hollow="log.action === 'remark'"
                            size="large"
                        >
                            <div class="log-content">
                                <div class="log-header">
                                    <span class="log-action">{{ getActionLabel(log.action) }}</span>
                                    <span class="log-operator">{{ log.operator_name || '系统' }}</span>
                                </div>
                                <div v-if="log.remark" class="log-remark">{{ log.remark }}</div>
                                <div v-if="log.from_status !== log.to_status" class="log-status-change">
                                    <el-tag size="small" type="info">{{ getStatusLabel(log.from_status) }}</el-tag>
                                    <el-icon><Right /></el-icon>
                                    <el-tag size="small" :type="getStatusType(log.to_status)">{{ getStatusLabel(log.to_status) }}</el-tag>
                                </div>
                            </div>
                        </el-timeline-item>
                    </el-timeline>
                </el-card>

                 <!-- 用户评价 -->
                <el-card v-if="order?.review" class="review-card" :shadow="isMobile ? 'never' : 'hover'">
                    <template #header>
                        <div class="card-title">
                            <el-icon><Star /></el-icon> 用户评价
                        </div>
                    </template>
                    <div class="review-content">
                        <div class="review-header">
                            <el-rate v-model="order.review.rating" disabled show-score text-color="#ff9900" />
                            <span class="review-time">{{ formatDate(order.review.created_at) }}</span>
                        </div>
                        <p class="review-text">{{ order.review.comment || '用户未填写文字评价' }}</p>
                    </div>
                </el-card>
            </el-col>

            <!-- 右侧侧边栏 -->
            <el-col :xs="24" :lg="8">
                <!-- 操作面板 (PC Only) -->
                <el-card v-if="!isMobile" class="action-card" shadow="hover">
                    <template #header>
                        <div class="card-title">工单操作</div>
                    </template>
                    
                    <div class="action-buttons">
                        <!-- 管理员: 派单 -->
                        <div v-if="canManageRepair && order?.status === 'pending'" class="action-group">
                             <el-button type="primary" class="block-btn" :disabled="assignSubmitting" @click="dialogAssignVisible = true">指派维修人员</el-button>
                             <el-button v-if="order?.assignee_id == null" class="block-btn" :loading="assignSubmitting" :disabled="assignSubmitting" @click="handleAutoAssign">自动智能派单</el-button>
                        </div>

                        <!-- 维修人员: 接单 -->
                         <div v-if="isMaintenance && order?.status === 'pending'" class="action-group">
                             <el-button type="primary" class="block-btn" @click="handleAccept">立即接单</el-button>
                         </div>

                        <!-- 处理中: 完成 -->
                        <div v-if="(isMaintenance || canManageRepair) && order?.status === 'processing'" class="action-group">
                             <el-button type="success" class="block-btn" @click="handleComplete">完成工单</el-button>
                        </div>

                        <!-- 通用: 取消 (仅未结束) -->
                         <div v-if="['pending', 'processing'].includes(order?.status)" class="action-group mt-4">
                             <el-popconfirm title="确定要取消这个工单吗？" @confirm="handleCancel">
                                <template #reference>
                                    <el-button type="danger" link>取消工单</el-button>
                                </template>
                             </el-popconfirm>
                         </div>

                         <div v-if="canDeleteOrder" class="action-group mt-4">
                             <el-button type="danger" class="block-btn" @click="handleDeleteOrder">删除工单</el-button>
                         </div>
                         
                         <div v-if="['completed', 'closed', 'cancelled'].includes(order?.status)" class="no-action">
                            当前状态无需操作
                         </div>
                    </div>
                </el-card>

                <!-- 基本信息卡片 -->
                <el-card class="meta-card" :shadow="isMobile ? 'never' : 'hover'">
                    <div class="meta-list">
                        <div class="meta-item">
                            <span class="label">报修人</span>
                            <span class="value">{{ order?.submitter_name }}</span>
                        </div>
                         <div class="meta-item">
                            <span class="label">当前处理人</span>
                            <span class="value">{{ order?.assignee_name || '-' }}</span>
                        </div>
                        <div class="meta-item">
                            <span class="label">创建时间</span>
                            <span class="value">{{ formatDate(order?.created_at) }}</span>
                        </div>
                        <div class="meta-item">
                            <span class="label">更新时间</span>
                            <span class="value">{{ formatDate(order?.updated_at) }}</span>
                        </div>
                    </div>
                </el-card>
            </el-col>
        </el-row>
    </div>

    <!-- Mobile Fixed Footer Actions -->
    <div v-if="isMobile && ['pending', 'processing'].includes(order?.status)" class="mobile-footer-actions">
        <!-- 管理员: 派单 -->
        <div v-if="canManageRepair && order?.status === 'pending'" class="action-group">
            <el-button type="primary" :disabled="assignSubmitting" @click="dialogAssignVisible = true">指派</el-button>
            <el-button v-if="order?.assignee_id == null" :loading="assignSubmitting" :disabled="assignSubmitting" @click="handleAutoAssign">自动派单</el-button>
        </div>

        <!-- 维修人员: 接单 -->
        <div v-if="isMaintenance && order?.status === 'pending'" class="action-group">
            <el-button type="primary" @click="handleAccept">接单</el-button>
        </div>

        <!-- 处理中: 完成 -->
        <div v-if="(isMaintenance || canManageRepair) && order?.status === 'processing'" class="action-group">
            <el-button type="success" @click="handleComplete">完成</el-button>
        </div>
        
        <!-- 通用: 取消 (仅未结束) -->
        <div v-if="['pending', 'processing'].includes(order?.status)" class="action-group">
            <el-popconfirm title="确定要取消吗？" @confirm="handleCancel">
                <template #reference>
                    <el-button type="danger" plain icon="Close">取消</el-button>
                </template>
            </el-popconfirm>
        </div>
    </div>

    <!-- 弹窗：派单 -->
    <el-dialog v-model="dialogAssignVisible" title="指派维修人员" width="400px" append-to-body>
        <el-form label-position="top">
            <el-form-item label="选择维修人员">
                <el-select v-model="assignForm.assignee_id" placeholder="请选择" style="width: 100%">
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
            <el-button type="primary" @click="handleAssign">确定指派</el-button>
        </template>
    </el-dialog>

    <!-- 弹窗：强制修改状态 -->
    <el-dialog v-model="dialogStatusVisible" title="修改工单状态" width="400px" append-to-body>
        <el-alert title="警告：强制修改状态可能会跳过正常的业务流程校验，请谨慎操作。" type="warning" :closable="false" class="mb-4" />
        <el-form label-position="top">
            <el-form-item label="新状态">
                <el-select v-model="statusForm.status" placeholder="请选择状态" style="width: 100%">
                    <el-option label="待受理 (Pending)" value="pending" />
                    <el-option label="处理中 (Processing)" value="processing" />
                    <el-option label="已完成 (Completed)" value="completed" />
                    <el-option label="已关闭 (Closed)" value="closed" />
                    <el-option label="已取消 (Cancelled)" value="cancelled" />
                    <el-option label="需补充信息 (Need Info)" value="need_info" />
                </el-select>
            </el-form-item>
             <el-form-item label="备注说明">
                <el-input v-model="statusForm.remark" type="textarea" placeholder="请输入修改原因..." />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="dialogStatusVisible = false">取消</el-button>
            <el-button type="primary" @click="handleForceUpdateStatus">保存修改</el-button>
        </template>
    </el-dialog>

    <!-- 弹窗：编辑工单 -->
    <el-dialog v-model="dialogEditVisible" title="编辑工单" width="520px" append-to-body>
        <el-form label-position="top">
            <el-form-item label="故障标题">
                <el-input v-model="editForm.title" maxlength="50" show-word-limit />
            </el-form-item>
            <el-form-item label="报修位置">
                <el-cascader
                    v-model="editForm.location_id"
                    :options="locationTreeData"
                    :props="{ value: 'id', label: 'label', children: 'children', checkStrictly: true, emitPath: false }"
                    placeholder="请选择故障位置"
                    clearable
                    filterable
                    style="width: 100%"
                    v-loading="locationTreeLoading"
                    :disabled="locationTreeForbidden"
                    :show-all-levels="false"
                />
            </el-form-item>
            <el-form-item label="紧急程度">
                <el-select v-model="editForm.priority" placeholder="请选择" style="width: 100%">
                    <el-option label="低" value="low" />
                    <el-option label="中" value="medium" />
                    <el-option label="高" value="high" />
                    <el-option label="紧急" value="emergency" />
                </el-select>
            </el-form-item>
            <el-form-item label="详细描述">
                <el-input v-model="editForm.description" type="textarea" :rows="5" resize="none" />
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="dialogEditVisible = false">取消</el-button>
            <el-button type="primary" :loading="editSubmitting" @click="submitEdit">保存</el-button>
        </template>
    </el-dialog>

    <!-- 弹窗：添加工作记录 -->
    <el-dialog v-model="dialogWorkLogVisible" title="添加工作记录" class="work-log-dialog" append-to-body>
        <el-form label-position="top">
            <el-form-item label="工作内容描述">
                <el-input 
                    v-model="workLogForm.content" 
                    type="textarea" 
                    :rows="4"
                    placeholder="请详细描述维修过程、更换配件或处理结果..." 
                />
            </el-form-item>
            <el-form-item label="上传现场照片" v-if="canUploadRepairImages">
                <div class="upload-options">
                    <div class="upload-btn camera" @click="triggerCamera">
                        <el-icon><Camera /></el-icon>
                        <span>拍照上传</span>
                    </div>
                    <div class="upload-btn gallery" @click="triggerGallery">
                        <el-icon><Picture /></el-icon>
                        <span>从相册选择</span>
                    </div>
                </div>

                <input type="file" ref="cameraInputRef" accept="image/*" capture="environment" style="display:none" @change="handleCustomUpload" />
                <input type="file" ref="galleryInputRef" accept="image/*" style="display:none" @change="handleCustomUpload" />

                <el-upload
                    v-model:file-list="repairImageFileList"
                    list-type="picture-card"
                    :before-upload="beforeRepairImageUpload"
                    :http-request="handleRepairImageUpload"
                    :on-remove="handleRepairImageRemove"
                    :on-success="handleRepairImageSuccess"
                    :limit="6"
                    class="hide-upload-btn"
                    accept="image/*"
                >
                    <template #trigger>
                        <!-- Hide default trigger -->
                    </template>
                </el-upload>
                <div class="el-upload__tip">支持上传图片并自动关联到本次工作记录。</div>
            </el-form-item>
            <el-form-item label="上传现场照片" v-else>
                <div class="el-upload__tip">无上传权限。</div>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="dialogWorkLogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleAddWorkLog" :loading="workLogSubmitting">提交记录</el-button>
        </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, computed, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { 
    ArrowLeft, Document, Location, Timer, Right, Star, 
    Edit, Refresh, Check, Tools, Plus, Monitor, Connection,
    Camera, Picture
} from '@element-plus/icons-vue';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import { getDeviceStatusTagType, getDeviceStatusText, isSshEnabled } from '@/components/DeviceList/deviceStatus';
import { homeDataStore } from '@/components/home/home/data';

const route = useRoute();
const router = useRouter();
const orderId = route.params.id;
const order = ref(null);
const loading = ref(false);
const nowTick = ref(Date.now())
let nowTimer = null
const roleCodes = ref([]);
const permissions = ref([]);
const isSuper = ref(false);
const currentUserId = ref(null);
const fullLocationPath = ref('');
const locationTreeLoading = ref(false);
const locationTreeLoaded = ref(false);
const locationTreeForbidden = ref(false);
const locationTreeData = ref([]);
const locationNodeById = reactive({});
const store = homeDataStore();

const isMobile = ref(window.innerWidth < 768)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }

// Dialogs
const dialogAssignVisible = ref(false);
const dialogStatusVisible = ref(false);
const dialogEditVisible = ref(false);
const dialogWorkLogVisible = ref(false);

// Data
const maintenanceUsers = ref([]);
const assignForm = reactive({ assignee_id: null });
const statusForm = reactive({ status: '', remark: '' });
const workLogForm = reactive({ content: '', images: [] });
const workLogSubmitting = ref(false);
const assignSubmitting = ref(false);
const editForm = reactive({ title: '', description: '', priority: 'medium', location_id: null });
const editSubmitting = ref(false);

const processedLogs = computed(() => {
    if (!order.value?.logs) return [];
    
    // Group logs by timestamp (seconds precision) to merge simultaneous actions
    const merged = [];
    const logs = [...order.value.logs]; // Copy
    
    // Sort just in case
    logs.sort((a, b) => new Date(a.created_at) - new Date(b.created_at));

    let lastLog = null;

    for (const log of logs) {
        // Skip redundant update_status logs if they happen same time as assign/auto_assign
        if (log.action === 'update_status' && lastLog) {
            const timeDiff = Math.abs(new Date(log.created_at) - new Date(lastLog.created_at));
            if (timeDiff < 2000 && ['assign', 'auto_assign', 'accept'].includes(lastLog.action)) {
                continue;
            }
        }
        
        // If current is assign/accept, it might update status too, so we prefer the specific action
        merged.push(log);
        lastLog = log;
    }
    
    return merged.reverse(); // Newest first
});

// Computeds
const canManageRepair = computed(() => isSuper.value || permissions.value.includes('sys:repair:manage'));
const isAdmin = computed(() => canManageRepair.value);
const isMaintenance = computed(() => roleCodes.value.includes('yunwei') || permissions.value.includes('sys:repair:accept'));
const canEditOrder = computed(() => {
    if (isSuper.value) return true;
    if (permissions.value.includes('sys:repair:manage')) return true;
    const uid = currentUserId.value;
    if (!uid || !order.value) return false;
    if (Number(order.value.submitter_id) !== Number(uid)) return false;
    if (order.value.status !== 'pending') return false;
    if (order.value.assignee_id != null) return false;
    return true;
});
const canDeleteOrder = computed(() => isSuper.value || permissions.value.includes('sys:repair:manage'));
const canUploadRepairImages = computed(() => isSuper.value || permissions.value.includes('sys:repair:image:add'));
const canDeleteRepairImages = computed(() => isSuper.value || permissions.value.includes('sys:repair:image:del'));
const canSsh = computed(() => isSuper.value || permissions.value.includes('sys:ssh:connect'));
const canViewRelatedDevices = computed(() => isSuper.value || permissions.value.includes('sys:device:list'));

const repairImageFileList = ref([]);
const repairImageIdByUid = reactive({});

const currentStep = computed(() => {
    if (!order.value) return 0;
    const s = order.value.status;
    // Step 0: 提交工单 (Created) - 0
    // Step 1: 待接单 (Pending) - 1
    // Step 2: 维修中 (Processing) - 2
    // Step 3: 已完成 (Completed) - 3
    // Step 4: 已评价 (Closed) - 5
    
    if (s === 'pending') return 1;
    if (s === 'processing') return 2;
    if (s === 'completed') return 3; 
    if (s === 'closed') return 5; // All done
    if (s === 'cancelled') return 0; 
    return 1;
});

// Helpers
const getPriorityLabel = (val) => ({ low: '低', medium: '中', high: '高', emergency: '紧急' }[val] || val);
const getPriorityType = (val) => ({ low: 'info', medium: 'warning', high: 'danger', emergency: 'danger' }[val] || '');

const getStatusLabel = (val) => {
    // Check if input is object (row) or string
    let status = val;
    let assigneeId = null;
    
    // Check if val is order object
    if (typeof val === 'object' && val !== null && 'status' in val) {
        status = val.status;
        assigneeId = val.assignee_id;
    }

    if (status === 'pending') {
        if (assigneeId) return '待接单';
        return '待受理'; // Detail view default
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

    if (typeof val === 'object' && val !== null && 'status' in val) {
        status = val.status;
        assigneeId = val.assignee_id;
    }

    if (status === 'pending') {
        if (assigneeId) return 'warning';
        return 'info';
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

const getActionLabel = (val) => ({
    create: '创建工单', assign: '指派工单', accept: '接单', complete: '完成工单', 
    auto_assign: '自动派单', cancel: '取消工单', review: '评价', update_status: '更新状态', remark: '添加备注', edit: '编辑工单'
}[val] || val);

const getLogType = (action) => {
    if (['create', 'assign', 'accept'].includes(action)) return 'primary';
    if (['complete', 'review'].includes(action)) return 'success';
    if (['cancel'].includes(action)) return 'danger';
    if (['update_status'].includes(action)) return 'warning';
    return '';
};

const formatDate = (str) => str ? new Date(str).toLocaleString() : '-';

const goBack = () => {
    router.push('/user/repair/list');
};

const buildLocationNodeIndex = (nodes) => {
    const stack = Array.isArray(nodes) ? [...nodes] : [];
    while (stack.length > 0) {
        const node = stack.pop();
        if (!node || node.id == null) continue;
        locationNodeById[String(node.id)] = node;
        const children = node.children;
        if (Array.isArray(children) && children.length > 0) {
            for (const c of children) stack.push(c);
        }
    }
};

const getLocationPathById = (nodeId) => {
    const labels = [];
    let cur = nodeId;
    const guard = new Set();
    while (cur != null && !guard.has(cur)) {
        guard.add(cur);
        const node = locationNodeById[String(cur)];
        if (!node) break;
        if (node.label) labels.push(String(node.label));
        cur = node.parent_id;
    }
    return labels.reverse().join(' / ');
};

const loadLocationTreeIfNeeded = async () => {
    if (locationTreeLoaded.value || locationTreeLoading.value || locationTreeForbidden.value) return;
    locationTreeLoading.value = true;
    try {
        const res = await axios.get('/api/v1/locations/tree');
        if (res?.data?.code === 200) {
            locationTreeData.value = res.data.data || [];
            buildLocationNodeIndex(locationTreeData.value);
            locationTreeLoaded.value = true;
        }
    } catch (e) {
        if (e?.response?.status === 403) {
            locationTreeForbidden.value = true;
        }
    } finally {
        locationTreeLoading.value = false;
    }
};

const updateFullLocationPath = async () => {
    fullLocationPath.value = '';
    if (!order.value?.location_id) return;
    await loadLocationTreeIfNeeded();
    if (!locationTreeLoaded.value) return;
    fullLocationPath.value = getLocationPathById(order.value.location_id);
};

const relatedDevices = ref([]);
const loadingDevices = ref(false);
const deviceFetchForbidden = ref(false);
const deviceFetchError = ref('');

const fetchRelatedDevices = async () => {
    if (!order.value?.location_id && !order.value?.location_name) {
        return;
    }
    
    loadingDevices.value = true;
    deviceFetchForbidden.value = false;
    deviceFetchError.value = '';
    try {
        const params = {};
        if (order.value.location_id) {
            params.location_node_id = order.value.location_id;
        } else {
            params.location = order.value.location_name;
        }
        
        const res = await axios.get('/api/v1/user/device/get', { params });
        let payload = res?.data;
        if (typeof payload === 'string') {
            try {
                payload = JSON.parse(payload);
            } catch {}
        }
        if (Array.isArray(payload)) {
            relatedDevices.value = payload;
            return;
        }
        if (payload && typeof payload === 'object') {
            if (payload.code === 200 && Array.isArray(payload.data)) {
                relatedDevices.value = payload.data || [];
                return;
            }
            if (Array.isArray(payload.data)) {
                relatedDevices.value = payload.data || [];
                return;
            }
        }
        relatedDevices.value = [];
        deviceFetchError.value = payload?.message || payload?.detail || '设备列表获取失败';
    } catch (e) {
        relatedDevices.value = [];
        const status = e?.response?.status;
        if (status === 403) {
            deviceFetchForbidden.value = true;
            deviceFetchError.value = '无权限查看该位置下的设备';
        } else {
            deviceFetchError.value = '设备列表获取失败';
        }
    } finally {
        loadingDevices.value = false;
    }
};

const handleSSH = (device) => {
    if (!canSsh.value) return;
    if (device?.ipv4) {
        let port = 22
        try {
            port = parseInt(String(device.ssh_port || device.port || 22), 10)
        } catch (e) {
            port = 22
        }
        if (!Number.isFinite(port) || port <= 0 || port > 65535) port = 22
        router.push({
            name: 'ssh-connection',
            params: { ip: device.ipv4 },
            query: { port: String(port) }
        });
    }
};

// API Actions
const fetchDetail = async () => {
    loading.value = true;
    try {
        const res = await axios.get(`/api/v1/repair-orders/${orderId}`);
        if (res.data.code === 200) {
            order.value = res.data.data;
            statusForm.status = order.value.status; // Init status form
            updateFullLocationPath();
            fetchRelatedDevices();
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
    try {
        const res = await axios.get('/api/v1/repair-orders/assignees');
        if (res.data.code === 200) {
            maintenanceUsers.value = res.data.data || [];
        }
    } catch (e) {}
};

const handleAssign = async () => {
    if (!assignForm.assignee_id) return;
    if (assignSubmitting.value) return;
    assignSubmitting.value = true;
    try {
        const res = await axios.post(`/api/v1/repair-orders/${orderId}/assign`, { assignee_id: assignForm.assignee_id });
        if (res.data.code === 200) {
            ElMessage.success('派单成功');
            dialogAssignVisible.value = false;
            fetchDetail();
        }
    } catch (e) {
        ElMessage.error('操作失败');
    } finally {
        assignSubmitting.value = false;
    }
};

const handleAutoAssign = async () => {
    if (assignSubmitting.value) return;
    if (order.value?.assignee_id != null) return;
    assignSubmitting.value = true;
    try {
        const res = await axios.post(`/api/v1/repair-orders/${orderId}/assign`, {});
        if (res.data.code === 200) {
            ElMessage.success('自动派单成功');
            fetchDetail();
        } else {
            ElMessage.error(res.data.message || '操作失败');
        }
    } catch (e) {
        ElMessage.error('操作失败');
    } finally {
        assignSubmitting.value = false;
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
    } catch (e) {}
};

const handleCancel = async () => {
     try {
        await ElMessageBox.prompt('请输入取消原因', '取消工单', {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            inputPattern: /\S+/,
            inputErrorMessage: '原因不能为空'
        }).then(async ({ value }) => {
            const res = await axios.post(`/api/v1/repair-orders/${orderId}/cancel`, { reason: value });
            if (res.data.code === 200) {
                ElMessage.success('工单已取消');
                fetchDetail();
            }
        });
    } catch (e) {}
}

const handleDeleteOrder = async () => {
    const id = order.value?.id ?? orderId;
    if (!id) return;
    try {
        await ElMessageBox.confirm('确定要删除该工单吗？此操作不可恢复。', '删除确认', {
            confirmButtonText: '确定删除',
            cancelButtonText: '取消',
            type: 'warning',
        });
        const res = await axios.delete(`/api/v1/repair-orders/${id}`);
        if (res.data.code === 200) {
            ElMessage.success('删除成功');
            router.push('/user/repair/list');
            return;
        }
        ElMessage.error(res.data.message || '删除失败');
    } catch (e) {
        return;
    }
}

const openEditDialog = async () => {
    if (!canEditOrder.value) return;
    if (!order.value) {
        await fetchDetail();
    }
    editForm.title = String(order.value?.title || '');
    editForm.description = String(order.value?.description || '');
    editForm.priority = String(order.value?.priority || 'medium') || 'medium';
    editForm.location_id = order.value?.location_id ?? null;
    dialogEditVisible.value = true;
    await loadLocationTreeIfNeeded();
}

const submitEdit = async () => {
    if (!canEditOrder.value) return;
    const title = String(editForm.title || '').trim();
    const description = String(editForm.description || '').trim();
    const priority = String(editForm.priority || '').trim();
    if (!title) {
        ElMessage.warning('请输入故障标题');
        return;
    }
    if (!description) {
        ElMessage.warning('请输入详细描述');
        return;
    }
    if (!priority) {
        ElMessage.warning('请选择紧急程度');
        return;
    }
    editSubmitting.value = true;
    try {
        const res = await axios.put(`/api/v1/repair-orders/${orderId}`, {
            title,
            description,
            priority,
            location_id: editForm.location_id
        });
        if (res.data.code === 200) {
            ElMessage.success('更新成功');
            dialogEditVisible.value = false;
            fetchDetail();
            return;
        }
        ElMessage.error(res.data.message || '更新失败');
    } catch (e) {
        ElMessage.error('更新失败');
    } finally {
        editSubmitting.value = false;
    }
}

const handleForceUpdateStatus = async () => {
    if (!statusForm.status) return;
    try {
        const res = await axios.post(`/api/v1/repair-orders/${orderId}/status`, {
            status: statusForm.status,
            remark: statusForm.remark
        });
        if (res.data.code === 200) {
            ElMessage.success('状态修改成功');
            dialogStatusVisible.value = false;
            fetchDetail();
        } else {
             ElMessage.error(res.data.message);
        }
    } catch (e) {
        ElMessage.error('修改失败');
    }
}

const handleRepairImageUpload = async (options) => {
    if (!canUploadRepairImages.value) {
        options?.onError?.(new Error('无上传权限'));
        return;
    }
    try {
        const formData = new FormData();
        formData.append('file', options.file);
        const res = await axios.post('/api/v1/repair-images/upload', formData, {
            headers: { 'Content-Type': 'multipart/form-data' }
        });
        if (res.data.code === 200) {
            options?.onSuccess?.(res.data, options.file);
        } else {
            options?.onError?.(new Error(res.data.message || '上传失败'));
        }
    } catch (e) {
        const status = e?.response?.status;
        if (status === 413) {
            ElMessage.error('图片过大(最大 20MB)');
        } else if (!e?.response) {
            const maxBytes = 20 * 1024 * 1024;
            const size = Number(options?.file?.size || 0);
            if (size > maxBytes) ElMessage.error('图片过大(最大 20MB)');
        }
        options?.onError?.(e);
    }
};

const beforeRepairImageUpload = (file) => {
    const maxBytes = 20 * 1024 * 1024;
    const type = String(file?.type || '');
    if (!type.startsWith('image/')) {
        ElMessage.error('仅支持图片文件');
        return false;
    }
    const size = Number(file?.size || 0);
    if (size > maxBytes) {
        ElMessage.error('图片过大(最大 20MB)');
        return false;
    }
    return true;
};

const handleRepairImageSuccess = (response, uploadFile) => {
    const id = response?.data?.id;
    const url = response?.data?.url;
    if (id) {
        repairImageIdByUid[uploadFile.uid] = id;
        if (!workLogForm.images.includes(id)) {
            workLogForm.images.push(id);
        }
    }
    if (url) {
        uploadFile.url = url;
    }
};

const cameraInputRef = ref(null);
const galleryInputRef = ref(null);

const triggerCamera = () => {
    cameraInputRef.value?.click();
};

const triggerGallery = () => {
    galleryInputRef.value?.click();
};

const handleCustomUpload = async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    
    if (!beforeRepairImageUpload(file)) {
        event.target.value = '';
        return;
    }

    const uid = Date.now();
    const uploadFile = reactive({
        uid: uid,
        name: file.name,
        status: 'uploading',
        percentage: 0,
        raw: file,
        url: URL.createObjectURL(file)
    });

    repairImageFileList.value.push(uploadFile);

    try {
        const options = {
            file: file,
            onSuccess: (res) => {
                uploadFile.status = 'success';
                handleRepairImageSuccess(res, uploadFile);
            },
            onError: (err) => {
                uploadFile.status = 'fail';
                const idx = repairImageFileList.value.indexOf(uploadFile);
                if (idx > -1) repairImageFileList.value.splice(idx, 1);
                ElMessage.error(err.message || '上传失败');
            }
        };
        await handleRepairImageUpload(options);
    } catch (e) {
        console.error(e);
    } finally {
        event.target.value = '';
    }
};

const handleRepairImageRemove = async (uploadFile) => {
    const id = repairImageIdByUid[uploadFile.uid];
    if (id) {
        workLogForm.images = workLogForm.images.filter(x => x !== id);
        delete repairImageIdByUid[uploadFile.uid];
        if (canDeleteRepairImages.value) {
            try {
                await axios.delete(`/api/v1/repair-images/${id}`);
            } catch (e) {}
        }
    }
};

const handleAddWorkLog = async () => {
    if (!workLogForm.content.trim()) {
        ElMessage.warning('请输入工作内容');
        return;
    }
    workLogSubmitting.value = true;
    try {
        const res = await axios.post(`/api/v1/repair-orders/${orderId}/work_logs`, {
            content: workLogForm.content,
            images: workLogForm.images
        });
        if (res.data.code === 200) {
            ElMessage.success('工作记录添加成功');
            dialogWorkLogVisible.value = false;
            workLogForm.content = '';
            workLogForm.images = [];
            repairImageFileList.value = [];
            Object.keys(repairImageIdByUid).forEach(k => delete repairImageIdByUid[k]);
            fetchDetail();
        } else {
            ElMessage.error(res.data.message || '添加失败');
        }
    } catch (e) {
        ElMessage.error('添加失败');
    } finally {
        workLogSubmitting.value = false;
    }
};

onMounted(async () => {
    nowTimer = window.setInterval(() => {
        nowTick.value = Date.now()
    }, 1000)
    store.syncAuthFromToken();
    try {
        const session = await store.ensureSession();
        if (session) {
            const roles = Array.isArray(store.roleCodes) ? store.roleCodes.map(r => String(r).toLowerCase()) : [];
            roleCodes.value = roles;
            isSuper.value = Boolean(store.isSuper);
            currentUserId.value = session?.id ?? null;
            const perms = await store.fetchPermissions();
            permissions.value = Array.isArray(perms) ? perms : [];
        }
    } catch {}
    fetchDetail();
    if (canManageRepair.value) {
        fetchMaintenanceUsers();
    }
});

onBeforeUnmount(() => {
    window.removeEventListener('resize', checkMobile)
    if (nowTimer) {
        clearInterval(nowTimer)
        nowTimer = null
    }
})
</script>

<style scoped>
.repair-detail-wrapper {
    min-height: 100%;
    background-color: #f5f7fa;
    padding-bottom: 40px;
}

.repair-detail-wrapper.is-mobile {
    padding-bottom: 80px; /* Space for fixed footer */
    background-color: #fff;
}

.page-header {
    background: #fff;
    padding: 16px 24px;
    box-shadow: 0 1px 4px rgba(0,21,41,.08);
    margin-bottom: 24px;
}

.is-mobile .page-header {
    padding: 12px 16px;
    margin-bottom: 0;
    border-bottom: 1px solid #f0f0f0;
    box-shadow: none;
    position: sticky;
    top: 0;
    z-index: 99;
}

.header-content {
    display: flex;
    align-items: center;
    gap: 12px;
}

.header-title {
    font-size: 20px;
    font-weight: 600;
    color: #1f2f3d;
    white-space: nowrap;
}

.is-mobile .header-title {
    font-size: 16px;
}

.main-content {
    max-width: 1200px;
    margin: 0 auto;
    padding: 0 20px;
}

.is-mobile .main-content {
    padding: 12px 16px;
}

/* Cards */
.step-card, .detail-card, .log-card, .review-card, .action-card, .meta-card, .device-card {
    margin-bottom: 20px;
    border-radius: 8px;
    border: none;
    box-shadow: 0 2px 12px 0 rgba(0,0,0,0.05) !important;
}

.is-mobile .step-card, 
.is-mobile .detail-card, 
.is-mobile .log-card, 
.is-mobile .review-card, 
.is-mobile .meta-card, 
.is-mobile .device-card {
    box-shadow: none !important;
    border: 1px solid #ebeef5;
    margin-bottom: 16px;
}

.card-title {
    font-size: 16px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Info Grid */
.info-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 20px;
}

.is-mobile .info-grid {
    grid-template-columns: 1fr;
    gap: 16px;
}

.info-item {
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.info-item.full-width {
    grid-column: span 2;
}

.is-mobile .info-item.full-width {
    grid-column: span 1;
}

.info-item label {
    font-size: 13px;
    color: #909399;
}

.info-item .content {
    font-size: 15px;
    color: #303133;
    display: flex;
    align-items: center;
    gap: 4px;
}

.title-text {
    font-weight: 600;
    font-size: 16px !important;
}

.description-box {
    background: #f8f9fa;
    padding: 12px;
    border-radius: 6px;
    line-height: 1.6;
    white-space: pre-wrap;
    color: #606266;
}

/* Action Buttons */
.action-buttons {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.block-btn {
    width: 100%;
    margin-left: 0 !important;
    margin-bottom: 8px;
}

.no-action {
    text-align: center;
    color: #909399;
    font-size: 13px;
    padding: 10px 0;
}

/* Mobile Fixed Footer */
.mobile-footer-actions {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: #fff;
    padding: 12px 16px;
    box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
    z-index: 100;
    display: flex;
    gap: 12px;
    align-items: center;
    justify-content: space-between;
}

.mobile-footer-actions .action-group {
    flex: 1;
    display: flex;
    gap: 8px;
}

.mobile-footer-actions .el-button {
    flex: 1;
    margin: 0;
}

/* Meta List */
.meta-list {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.meta-item {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
}

.meta-item .label {
    color: #909399;
}

.meta-item .value {
    color: #606266;
    font-family: monospace;
}

/* Log Styles */
.work-log-card {
    margin-bottom: 20px;
}
.work-log-item {
    border-bottom: 1px solid #ebeef5;
    padding: 16px 0;
}
.work-log-item:last-child {
    border-bottom: none;
    padding-bottom: 0;
}
.work-log-item:first-child {
    padding-top: 0;
}
.work-log-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 8px;
    font-size: 13px;
    color: #909399;
}
.work-log-header .operator {
    font-weight: 600;
    color: #303133;
}
.work-log-content {
    font-size: 14px;
    color: #606266;
    line-height: 1.6;
    white-space: pre-wrap;
}
.work-log-images {
    margin-top: 10px;
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.order-images {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}
.log-image {
    width: 80px;
    height: 80px;
    border-radius: 4px;
    border: 1px solid #ebeef5;
}

.log-content {
    background: #f8f9fa;
    padding: 10px 14px;
    border-radius: 6px;
}

.log-header {
    display: flex;
    justify-content: space-between;
    margin-bottom: 4px;
}

.log-action {
    font-weight: 600;
    color: #303133;
}

.log-operator {
    font-size: 12px;
    color: #909399;
}

.log-remark {
    font-size: 13px;
    color: #606266;
    margin-top: 4px;
}

.log-status-change {
    margin-top: 8px;
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
}

.review-content {
    background: #fff9e6;
    padding: 16px;
    border-radius: 6px;
}

.review-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}

.review-time {
    font-size: 12px;
    color: #909399;
}

.review-text {
    color: #606266;
    line-height: 1.5;
}

.mb-4 {
    margin-bottom: 16px;
}
.mt-4 {
    margin-top: 16px;
}

/* Upload Options */
.upload-options {
    display: flex;
    gap: 16px;
    margin-bottom: 16px;
    width: 100%;
}

.upload-btn {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 20px;
    background: #f5f7fa;
    border: 1px dashed #dcdfe6;
    border-radius: 8px;
    cursor: pointer;
    transition: all 0.3s;
    color: #606266;
}

.upload-btn:hover {
    border-color: #409eff;
    color: #409eff;
    background: #ecf5ff;
}

.upload-btn .el-icon {
    font-size: 24px;
    margin-bottom: 8px;
}

.upload-btn span {
    font-size: 14px;
}

:deep(.hide-upload-btn .el-upload--picture-card) {
    display: none;
}
</style>

<style>
/* Global overrides for append-to-body dialogs */
.work-log-dialog {
    width: 500px;
    border-radius: 12px !important;
}

@media (max-width: 768px) {
    .work-log-dialog {
        width: 90% !important;
    }

    /* 修复手机端头部错乱 */
    .page-header :deep(.el-page-header__header) {
        flex-wrap: wrap;
        gap: 8px;
    }

    .page-header :deep(.el-page-header__left) {
        margin-right: 0;
    }

    .page-header :deep(.el-page-header__content) {
        flex: 1;
        overflow: hidden;
        margin-right: 8px;
    }

    .header-title {
        font-size: 16px;
    }

    .header-content {
        gap: 8px;
    }

    /* 移动端修改状态按钮变小一点 */
    .status-btn-mobile {
        padding: 8px 10px;
        height: 32px;
    }

    /* Element Plus 自带的 hidden-xs-only 类可能需要 display-none */
    .hidden-xs-only {
        display: none !important;
    }
}
</style>
