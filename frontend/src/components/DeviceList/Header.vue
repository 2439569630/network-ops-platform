<template>
    <div class="device-list-container" :class="{ 'is-mobile': isMobile }">
        <div class="device-list-header">
            <!-- Mobile Tabs Row (Above Search) -->
            <div class="header-tabs-row" v-if="isMobile">
                 <el-tabs v-model="activeTab" @tab-click="handleTabClick" class="mobile-tabs-header">
                    <el-tab-pane label="全部" name="0"></el-tab-pane>
                    <el-tab-pane label="路由" name="1"></el-tab-pane>
                    <el-tab-pane label="交换" name="2"></el-tab-pane>
                    <el-tab-pane label="防火" name="3"></el-tab-pane>
                    <el-tab-pane label="服务" name="4"></el-tab-pane>
                </el-tabs>
            </div>

            <div class="header-left" v-if="!isMobile">
                <h1 class="page-title">设备管理</h1>
                <p class="page-subtitle">管理网络设备</p>
            </div>

            <div class="header-center">
                <div class="search-box">
                    <el-input 
                        v-model="searchInput" 
                        class="search-input"
                        placeholder="搜索设备..." 
                        :prefix-icon="Search"
                        clearable
                        @clear="handleSearch"
                        @keyup.enter="handleSearch"
                    />
                    <el-button 
                        type="primary" 
                        @click="handleSearch()" 
                        class="search-btn"
                        :icon="Search"
                        circle
                        v-if="isMobile"
                    />
                     <el-button 
                        type="primary" 
                        @click="handleSearch()" 
                        class="search-btn"
                        v-else
                    >
                        搜索
                    </el-button>
                </div>
            </div>

            <div class="header-right">
                <el-button 
                    type="primary" 
                    :icon="Plus" 
                    @click="addDevice"
                    class="action-btn primary"
                    :circle="isMobile"
                >
                    <span v-if="!isMobile">添加设备</span>
                </el-button>
                <el-button
                    v-if="canRecycle && !isMobile"
                    type="warning"
                    :icon="Delete"
                    @click="goRecyclePage"
                    class="action-btn"
                >
                    回收站
                </el-button>
                 <el-button
                    v-if="canRecycle && isMobile"
                    type="warning"
                    :icon="Delete"
                    @click="goRecyclePage"
                    class="action-btn"
                    circle
                />
                
            </div>
        </div>

        <!-- 添加设备弹窗 -->
        <el-dialog 
            v-model="dialogFormVisible" 
            title="添加新设备" 
            :width="isMobile ? '90%' : '600px'"
            class="device-dialog"
            center
            :close-on-click-modal="false"
            destroy-on-close
            append-to-body
        >
            <el-form 
                :model="deviceForm" 
                :rules="rules" 
                ref="deviceFormRef" 
                :label-width="isMobile ? '70px' : '90px'"
                label-position="right"
                class="device-form"
                status-icon
            >
                <!-- 基本信息 -->
                <div class="form-section-title">基本信息</div>
                <div class="form-row">
                    <el-form-item label="设备名称" prop="device_name" class="form-item">
                        <el-input 
                            v-model="deviceForm.device_name" 
                            placeholder="例如: Core-Router-01" 
                        />
                    </el-form-item>
                    
                    <el-form-item label="设备类型" prop="type" class="form-item">
                        <el-select 
                            v-model="deviceForm.type" 
                            placeholder="请选择"
                            style="width: 100%"
                        >
                            <el-option label="路由器" value="路由器" />
                            <el-option label="交换机" value="交换机" />
                            <el-option label="防火墙" value="防火墙" />
                            <el-option label="服务器" value="服务器" />
                        </el-select>
                    </el-form-item>
                </div>

                <!-- 连接信息 -->
                <div class="form-section-title">连接信息</div>
                <div class="form-row">
                    <el-form-item label="IPv4地址" prop="ipv4" class="form-item" style="flex: 2">
                        <el-input 
                            v-model="deviceForm.ipv4" 
                            placeholder="例如: 192.168.1.1" 
                        />
                    </el-form-item>
                    <el-form-item label="SSH端口" prop="ssh_port" class="form-item" style="flex: 1">
                        <el-input-number 
                            v-model="deviceForm.ssh_port" 
                            :min="1" 
                            :max="65535"
                            style="width: 100%"
                            controls-position="right"
                        />
                    </el-form-item>
                </div>

                <div class="form-row">
                    <el-form-item label="账号" prop="user_name" class="form-item">
                        <el-input 
                            v-model="deviceForm.user_name" 
                            placeholder="登录用户名" 
                            :prefix-icon="User"
                        />
                    </el-form-item>

                    <el-form-item label="密码" prop="password" class="form-item">
                        <el-input 
                            v-model="deviceForm.password" 
                            type="password"
                            placeholder="登录密码" 
                            show-password
                            :prefix-icon="Lock"
                        />
                    </el-form-item>
                </div>

                <!-- 其他信息 -->
                <div class="form-section-title">其他信息</div>
                <div class="form-row">
                    <el-form-item label="MAC地址" prop="mac" class="form-item">
                        <el-input 
                            v-model="deviceForm.mac" 
                            placeholder="例如: 00:1B:44:11:3A:B7" 
                        />
                    </el-form-item>
                    <el-form-item label="位置" prop="location" class="form-item">
                        <el-input 
                            v-model="deviceForm.location" 
                            placeholder="例如: 机房A-01柜" 
                            :prefix-icon="Location"
                        />
                    </el-form-item>
                </div>
                
                <el-form-item label="IPv6地址" prop="ipv6" class="full-width">
                    <el-input 
                        v-model="deviceForm.ipv6" 
                        placeholder="例如: 2001:0db8:85a3:0000:0000:8a2e:0370:7334" 
                    />
                </el-form-item>
            </el-form>
            
            <template #footer>
                <div class="dialog-footer">
                    <div class="footer-left">
                        <el-button 
                            @click="testConnect" 
                            class="test-btn"
                            :loading="testing"
                            :icon="Connection"
                            plain
                            type="warning"
                        >
                            {{ testing ? '测试' : (isMobile ? '测试' : '测试连接') }}
                        </el-button>
                    </div>
                    <div class="footer-right">
                        <el-button @click="closeDialog">取消</el-button>
                        <el-button 
                            type="primary" 
                            @click="submitForm"
                            :loading="submitting"
                        >
                            确定
                        </el-button>
                    </div>
                </div>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
import { Plus, Upload, Search, Connection, User, Lock, Location, Delete } from '@element-plus/icons-vue'
import { computed, onMounted, onBeforeUnmount, ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import { useDeviceStore } from './store' 
import { homeDataStore } from '@/components/home/home/data'

const store = useDeviceStore() 
const authStore = homeDataStore()
const router = useRouter()

// 移动端检测
const isMobile = ref(false)
let mobileMediaQuery = null
let mobileMediaListener = null

// Tab State for Mobile Header
const activeTab = ref('0')

// 搜索输入
const searchInput = ref('')

// 表单显示状态
const dialogFormVisible = ref(false)
const testing = ref(false)
const submitting = ref(false)

const canRecycle = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:del')))

onMounted(() => {
    authStore.syncAuthFromToken()
    authStore.fetchPermissions()
    
    // Mobile Check
    mobileMediaQuery = window.matchMedia('(max-width: 768px)')
    mobileMediaListener = () => {
        isMobile.value = mobileMediaQuery.matches
    }
    mobileMediaListener()
    if (mobileMediaQuery.addEventListener) {
        mobileMediaQuery.addEventListener('change', mobileMediaListener)
    } else {
        mobileMediaQuery.addListener(mobileMediaListener)
    }
})

onBeforeUnmount(() => {
    if (mobileMediaQuery && mobileMediaListener) {
        if (mobileMediaQuery.removeEventListener) {
            mobileMediaQuery.removeEventListener('change', mobileMediaListener)
        } else {
            mobileMediaQuery.removeListener(mobileMediaListener)
        }
    }
})

// 设备表单
const deviceForm = reactive({
    device_name: '',
    user_name: '',
    password: '',
    type: '',
    ipv4: '',
    ipv6: '',
    mac: '',
    location: '',
    ssh_port: 22,
    status: '在线'
})

// 表单验证规则
const rules = reactive({
    device_name: [
        { required: true, message: '请输入设备名称', trigger: 'blur' }
    ],
    type: [
        { required: true, message: '请选择设备类型', trigger: 'change' }
    ],
    ipv4: [
        { required: true, message: '请输入IPv4地址', trigger: 'blur' },
        { 
            pattern: /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/,
            message: 'IPv4格式不正确',
            trigger: 'blur'
        }
    ],
    ssh_port: [
        { required: true, message: '请输入端口', trigger: 'blur' },
        { type: 'number', message: '必须为数字', trigger: 'blur' }
    ],
    mac: [
        // { required: false, message: 'MAC地址', trigger: 'blur' },
        {
            pattern: /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/,
            message: 'MAC地址格式不正确',
            trigger: 'blur'
        }
    ],
    user_name: [
        { required: true, message: '请输入账号', trigger: 'blur' }
    ],
    password: [
        { required: true, message: '请输入密码', trigger: 'blur' }
    ]
})

// 表单引用
const deviceFormRef = ref()

// 搜索事件
const handleSearch = () => {
    // 调用 Store 的搜索方法
    store.setSearchQuery(searchInput.value)
    // store.refreshData() // store 内部如果需要自动刷新会在 setSearchQuery 处理，或者这里显式调用
    store.refreshData()
}

const handleTabClick = (tab) => {
    store.clearData();
    store.setdataCardType(0); // Ensure card view
    store.getServerDveiceData(tab.paneName);
};

// 打开添加设备弹窗
const addDevice = () => {
    dialogFormVisible.value = true
}

// 关闭弹窗
const closeDialog = () => {
    dialogFormVisible.value = false
    // 重置表单
    if (deviceFormRef.value) {
        deviceFormRef.value.resetFields()
        deviceForm.ssh_port = 22 // 重置端口默认值
    }
}

const goRecyclePage = () => {
    router.push({ name: 'device-recycle' })
}

// 提交表单
const submitForm = () => {
    if (!deviceFormRef.value) return
    
    deviceFormRef.value.validate(async (valid) => {
        if (valid) {
            submitting.value = true
            try {
                const res = await axios.post('/api/v1/user/device/add', deviceForm)
                if (res.data.code === 200) {
                    ElMessage.success('设备添加成功')
                    closeDialog()
                    // 刷新列表
                    store.refreshData()
                } else {
                    ElMessage.error(res.data.message || '添加失败')
                }
            } catch (error) {
                console.error('添加设备错误:', error)
                ElMessage.error('添加设备失败')
            } finally {
                submitting.value = false
            }
        }
    })
}

// 测试连接
const testConnect = async () => {
    // 简单验证必要字段
    if (!deviceForm.ipv4 || !deviceForm.user_name || !deviceForm.password || !deviceForm.type) {
        ElMessage.warning('请先填写设备类型、IPv4、账号和密码')
        return
    }

    testing.value = true
    try {
        const res = await axios.post('/api/v1/user/device/test_connect', {
            ipv4: deviceForm.ipv4,
            ssh_port: deviceForm.ssh_port,
            user_name: deviceForm.user_name,
            password: deviceForm.password,
            type: deviceForm.type
        })
        
        if (res.data.code === 200) {
            ElMessage.success('连接测试成功')
        } else {
            ElMessage.error(res.data.message || '连接测试失败')
        }
    } catch (error) {
        console.error('SSH连接测试错误:', error);
        ElMessage.error('连接测试请求发生错误')
    } finally {
        testing.value = false
    }
}
</script>

<style scoped>
.device-list-container {
    width: 100%;
    margin-top: 20px;
}

.device-list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #fff;
    padding: 24px;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.05);
    flex-wrap: wrap;
    gap: 20px;
}

.header-left {
    display: flex;
    flex-direction: column;
}

.page-title {
    font-size: 24px;
    font-weight: 600;
    color: #1f2937;
    margin: 0 0 4px 0;
}

.page-subtitle {
    font-size: 14px;
    color: #9ca3af;
    margin: 0;
}

.header-center {
    flex: 1;
    display: flex;
    justify-content: center;
}

.search-box {
    display: flex;
    align-items: center;
    max-width: 480px;
    width: 100%;
    gap: 12px;
}

.search-input {
    flex: 1;
}

.search-input :deep(.el-input__wrapper) {
    border-radius: 8px;
    padding: 4px 12px;
    box-shadow: 0 0 0 1px #e5e7eb inset;
}

.search-input :deep(.el-input__wrapper.is-focus) {
    box-shadow: 0 0 0 2px #3b82f6 inset;
}

.search-btn {
    border-radius: 8px;
    padding: 0 24px;
    height: 40px;
}

.header-right {
    display: flex;
    gap: 12px;
}

.action-btn {
    border-radius: 8px;
    height: 40px;
    padding: 0 20px;
}

/* 弹窗样式优化 */
.device-dialog :deep(.el-dialog) {
    border-radius: 16px;
    overflow: hidden;
    box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
}

.device-dialog :deep(.el-dialog__header) {
    padding: 20px 24px;
    background: #f9fafb;
    border-bottom: 1px solid #e5e7eb;
    margin-right: 0;
}

.device-dialog :deep(.el-dialog__title) {
    font-size: 18px;
    font-weight: 600;
    color: #111827;
}

.device-dialog :deep(.el-dialog__body) {
    padding: 24px 32px;
}

.form-section-title {
    font-size: 14px;
    font-weight: 600;
    color: #374151;
    margin-bottom: 16px;
    padding-left: 8px;
    border-left: 3px solid #3b82f6;
    line-height: 1;
}

.device-form {
    padding: 4px 0;
}

.form-row {
    display: flex;
    gap: 24px;
    margin-bottom: 8px;
}

.form-item {
    flex: 1;
}

.full-width {
    width: 100%;
}

.device-form :deep(.el-form-item__label) {
    font-weight: 500;
    color: #4b5563;
}

.device-form :deep(.el-input__wrapper),
.device-form :deep(.el-select__wrapper) {
    border-radius: 6px;
    box-shadow: 0 0 0 1px #d1d5db inset;
}

.dialog-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 8px;
}

.footer-left {
    display: flex;
    align-items: center;
}

.footer-right {
    display: flex;
    gap: 12px;
}

/* 响应式适配 */
@media (max-width: 768px) {
    /* Minimalist Mobile Header */
    .device-list-container.is-mobile {
        margin-top: 0;
        background: #fff;
    }

    .device-list-header {
        padding: 12px 16px;
        box-shadow: 0 4px 12px rgba(255, 255, 255, 0.9); /* Add white shadow/glow to mask underlying content */
        border-bottom: 1px solid #f0f0f0;
        border-radius: 0;
        background: #fff; /* Ensure solid white background */
        gap: 12px;
        flex-direction: column; /* Stack tabs and search */
        align-items: stretch;
        justify-content: flex-start;
        position: relative;
        top: auto;
        z-index: 101; /* High z-index to stay above Tabs */
    }

    .header-tabs-row {
        width: 100%;
        margin-bottom: 4px;
        border-bottom: 1px solid #f0f0f0;
    }
    
    .mobile-tabs-header :deep(.el-tabs__header) {
        margin: 0;
    }

    .mobile-tabs-header :deep(.el-tabs__nav-wrap::after) {
        height: 0;
    }

    .mobile-tabs-header :deep(.el-tabs__item) {
        font-size: 15px;
        color: #64748b;
        font-weight: 500;
        height: 40px;
        line-height: 40px;
        padding: 0 16px;
    }

    .mobile-tabs-header :deep(.el-tabs__item.is-active) {
        color: #1e3a8a;
        font-weight: 600;
    }

    .mobile-tabs-header :deep(.el-tabs__active-bar) {
        background-color: #1e3a8a;
        height: 3px;
        border-radius: 3px;
    }

    .header-center {
        order: 2;
        flex: none;
        width: 100%;
        display: flex;
        justify-content: space-between; /* Align search and buttons */
        align-items: center;
    }

    .search-box {
        max-width: none;
        width: auto;
        flex: 1;
        gap: 8px;
        margin-right: 8px;
    }
    
    .header-right {
        order: 2; /* Same line as search */
        gap: 8px;
        flex-shrink: 0;
    }
    
    .action-btn {
        height: 36px;
        width: 36px;
        padding: 0;
        border: none;
        background: transparent;
        color: #1e3a8a; /* Primary Blue */
        box-shadow: none;
    }
    
    .action-btn:hover, .action-btn:active {
        background: rgba(30, 58, 138, 0.05);
        color: #1e3a8a;
    }

    .action-btn.primary {
        background: #1e3a8a;
        color: #fff;
        box-shadow: 0 4px 10px rgba(30, 58, 138, 0.3); /* Subtle shadow */
    }

    /* Dialog Mobile Optimization */
    .device-dialog :deep(.el-dialog) {
        border-radius: 20px; /* Modern rounded corners */
        margin-top: 10vh !important;
    }
    
    .device-dialog :deep(.el-dialog__header) {
        padding: 20px;
        background: #fff;
        border-bottom: none;
        text-align: left;
    }
    
    .device-dialog :deep(.el-dialog__title) {
        color: #1e3a8a;
        font-size: 20px;
        font-weight: 700;
    }
    
    .device-dialog :deep(.el-dialog__body) {
        padding: 0 20px 20px;
    }
    
    .form-section-title {
        color: #1e3a8a;
        border-left: 3px solid #1e3a8a;
        font-size: 15px;
        margin-top: 12px;
    }
    
    .form-row {
        flex-direction: column;
        gap: 0;
    }
    
    .dialog-footer {
        flex-direction: column-reverse;
        gap: 12px;
        padding-top: 10px;
    }
    
    .footer-left, .footer-right {
        width: 100%;
        justify-content: center;
    }
    
    .footer-right {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 12px;
    }
    
    .footer-right button {
        width: 100%;
        height: 44px; /* Taller for touch */
        border-radius: 12px;
        font-weight: 600;
    }
    
    .footer-right button.el-button--primary {
        background: #1e3a8a;
        border-color: #1e3a8a;
        box-shadow: 0 4px 12px rgba(30, 58, 138, 0.25);
    }
    
    .test-btn {
        width: 100%;
        border-radius: 12px;
        height: 40px;
    }
}
</style>
