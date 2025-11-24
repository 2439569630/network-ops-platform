<template>
    <div class="device-list-container">
        <div class="device-list-header">
            <div class="header-left">
                <h1 class="page-title">设备管理</h1>
                <p class="page-subtitle">管理系统中的所有网络设备</p>
            </div>

            <div class="header-center">
                <div class="search-box">
                    <el-input 
                        v-model="searchInput" 
                        class="search-input"
                        placeholder="搜索设备名称、IP地址或位置..." 
                        :prefix-icon="Search"
                        clearable
                    />
                    <el-button 
                        type="primary" 
                        @click="handleSearch()" 
                        class="search-btn"
                    >
                        搜索
                    </el-button>
                </div>
            </div>

            <div class="header-right">
                <el-button 
                    type="primary" 
                    :icon="Plus" 
                    @click="dialogFormVisible = true"
                    class="action-btn primary"
                >
                    添加设备
                </el-button>
                <el-button 
                    type="success" 
                    :icon="Upload"
                    class="action-btn"
                >
                    导出设备
                </el-button>
            </div>
        </div>

        <!-- 添加设备弹窗 -->
        <el-dialog 
            v-model="dialogFormVisible" 
            title="添加新设备" 
            width="650px" 
            
            class="device-dialog"
            center
        >
            <el-form 
                :model="deviceForm" 
                :rules="rules" 
                ref="deviceFormRef" 
                label-width="100px"
                label-position="left"
                class="device-form"
            >
                <div class="form-row">
                    <el-form-item label="设备名称" prop="device_name" class="form-item">
                        <el-input 
                            v-model="deviceForm.device_name" 
                            placeholder="请输入设备名称" 
                            size="large"
                        />
                    </el-form-item>
                    
                    <el-form-item label="设备类型" prop="type" class="form-item">
                        <el-select 
                            v-model="deviceForm.type" 
                            placeholder="请选择设备类型"
                            size="large"
                            style="width: 100%"
                        >
                            <el-option label="路由器" value="路由器" />
                            <el-option label="交换机" value="交换机" />
                            <el-option label="防火墙" value="防火墙" />
                            <el-option label="服务器" value="服务器" />
                        </el-select>
                    </el-form-item>
                </div>
                
                <div class="form-row">
                    <el-form-item label="IPv4地址" prop="ipv4" class="form-item">
                        <el-input 
                            v-model="deviceForm.ipv4" 
                            placeholder="例如: 192.168.1.1" 
                            size="large"
                        />
                    </el-form-item>

                    <el-form-item label="MAC地址" prop="mac" class="form-item">
                        <el-input 
                            v-model="deviceForm.mac" 
                            placeholder="例如: 00-1B-44-11-3A-B7" 
                            size="large"
                        />
                    </el-form-item>
                </div>
                
                <el-form-item label="IPv6地址" class="full-width">
                    <el-input 
                        v-model="deviceForm.ipv6" 
                        placeholder="例如: 2001:0db8:85a3:0000:0000:8a2e:0370:7334" 
                        size="large"
                    />
                </el-form-item>
                
                <div class="form-row">
                    <el-form-item label="账号" prop="user_name" class="form-item">
                        <el-input 
                            v-model="deviceForm.user_name" 
                            placeholder="请输入登录账号" 
                            size="large"
                        />
                    </el-form-item>

                    <el-form-item label="密码" prop="password" class="form-item">
                        <el-input 
                            v-model="deviceForm.password" 
                            type="password"
                            placeholder="请输入登录密码" 
                            size="large"
                            show-password
                        />
                    </el-form-item>
                </div>
                
                <el-form-item label="位置" prop="location" class="full-width">
                    <el-input 
                        v-model="deviceForm.location" 
                        placeholder="请输入设备物理位置" 
                        size="large"
                    />
                </el-form-item>
            </el-form>
            
            <template #footer>
                <div class="dialog-footer">
                    <el-button 
                        @click="testConnect()" 
                        class="test-btn"
                        :icon="Connection"
                    >
                        测试连接
                    </el-button>
                    <div>
                        <el-button 
                            @click="closeDialog" 
                            class="cancel-btn"
                        >
                            取消
                        </el-button>
                        <el-button 
                            type="primary" 
                            @click="submitForm"
                            class="confirm-btn"
                        >
                            添加设备
                        </el-button>
                    </div>
                </div>
            </template>
        </el-dialog>
    </div>
</template>

<script setup>
import { Plus, Upload, Search, Connection } from '@element-plus/icons-vue'
import { ref, reactive } from 'vue'
import axios from '@/axios/axios'

// 搜索输入
const searchInput = ref('')

// 表单显示状态
const dialogFormVisible = ref(false)

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
            message: '请输入正确的IPv4地址格式',
            trigger: 'blur'
        }
    ],
    mac: [
        { required: false, message: 'MAC地址', trigger: 'blur' },
        {
            pattern: /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/,
            message: '请输入正确的MAC地址格式',
            trigger: 'blur'
        }
    ],
    location: [
        { required: false, message: '请输入设备位置', trigger: 'blur' }
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
    console.log('搜索', searchInput.value)
}

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
    }
}

// 提交表单
const submitForm = () => {
    if (!deviceFormRef.value) return
    
    deviceFormRef.value.validate((valid) => {
        if (valid) {
            axios.post('/user/device/add', deviceForm).then((res) => {
                
            })
            closeDialog()
        } else {
            console.log('表单验证失败')
            return false
        }
    })
}

// 测试连接
const testConnect = async () => {
   try {
        const baseURL = axios.defaults.baseURL;
        const response = await fetch(`${baseURL}/user/device/add`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                credentials: 'include'
            },
            body: JSON.stringify({
                ...deviceForm,
            })
        });

        if (!response.ok) {
            throw new Error(`SSH连接测试失败: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';

        while (true) {
            const { done, value } = await reader.read();
            
            if (done) {
                console.log('SSH测试完成');
                break;
            }

            const chunk = decoder.decode(value);
            fullResponse += chunk;
        }
        
        return fullResponse;
    } catch (error) {
        console.error('SSH连接测试错误:', error);
    }
}
</script>

<style scoped>
.device-list-container {
    width: 100%;
    background: none;
    margin-top: 20px;
}

.device-list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #fff;
    padding: 24px;
    border-radius: 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    flex-wrap: wrap;
    gap: 20px;
}

.header-left {
    display: flex;
    flex-direction: column;
    flex: 1;
    min-width: 200px;
}

.page-title {
    font-size: 24px;
    font-weight: 600;
    color: #1f2937;
    margin: 0 0 4px 0;
}

.page-subtitle {
    font-size: 14px;
    color: #6b7280;
    margin: 0;
}

.header-center {
    display: flex;
    justify-content: center;
    flex: 2;
    min-width: 300px;
}

.search-box {
    display: flex;
    align-items: center;
    max-width: 400px;
    width: 100%;
}

.search-input {
    flex: 1;
    margin-right: 8px;
}

.search-input :deep(.el-input__inner) {
    border-radius: 8px;
    height: 40px;
}

.search-btn {
    height: 40px;
    border-radius: 8px;
    padding: 0 20px;
}

.header-right {
    display: flex;
    justify-content: flex-end;
    flex: 1;
    min-width: 250px;
    gap: 12px;
}

.action-btn {
    height: 40px;
    border-radius: 8px;
    font-weight: 500;
    padding: 0 16px;
}

.action-btn.primary {
    background: linear-gradient(135deg, #3b82f6, #1d4ed8);
    border: none;
}

.action-btn.primary:hover {
    background: linear-gradient(135deg, #1d4ed8, #1e40af);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3);
}

/* 弹窗样式 */
.device-dialog :deep(.el-dialog) {
    border-radius: 12px;
    box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
}

.device-dialog :deep(.el-dialog__header) {
    padding: 24px 24px 16px;
    border-bottom: 1px solid #f0f0f0;
    margin-right: 0;
}

.device-dialog :deep(.el-dialog__title) {
    font-size: 20px;
    font-weight: 600;
    color: #1f2937;
}

.device-dialog :deep(.el-dialog__body) {
    padding: 24px;
}

.device-form {
    padding: 0 8px;
}

.form-row {
    display: flex;
    gap: 20px;
}

.form-item, .full-width {
    flex: 1;
}

.full-width {
    width: 100%;
}

.device-form :deep(.el-form-item__label) {
    font-weight: 500;
    color: #374151;
    padding-bottom: 8px;
}

.device-form :deep(.el-input__inner) {
    border-radius: 8px;
    height: 40px;
}

.device-form :deep(.el-select) {
    width: 100%;
}

.dialog-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding-top: 16px;
    border-top: 1px solid #f0f0f0;
}

.test-btn {
    color: #3b82f6;
    border-color: #3b82f6;
}

.test-btn:hover {
    background: #eff6ff;
    color: #1d4ed8;
    border-color: #1d4ed8;
}

.cancel-btn {
    margin-right: 12px;
}

.confirm-btn {
    background: linear-gradient(135deg, #3b82f6, #1d4ed8);
    border: none;
    padding: 0 24px;
}

.confirm-btn:hover {
    background: linear-gradient(135deg, #1d4ed8, #1e40af);
    transform: translateY(-1px);
}

/* 响应式设计 */
@media (max-width: 1024px) {
    .device-list-header {
        flex-direction: column;
        align-items: stretch;
        gap: 20px;
    }
    
    .header-left, .header-center, .header-right {
        justify-content: center;
        min-width: auto;
    }
    
    .header-right {
        justify-content: center;
    }
}

@media (max-width: 768px) {
    .device-list-container {
        padding: 12px;
    }
    
    .device-list-header {
        padding: 16px;
    }
    
    .form-row {
        flex-direction: column;
        gap: 0;
    }
    
    .dialog-footer {
        flex-direction: column;
        gap: 12px;
    }
    
    .dialog-footer > div {
        width: 100%;
        display: flex;
        justify-content: flex-end;
    }
}
</style>