<template>
    <div class="DeviceList-Header-box">
        <div class="DeviceList-Header-box-left DeviceList-Header-box-item2">
            <h1>设备管理</h1>
            <!-- <el-divider /> -->
        </div>

        <div class="DeviceList-Header-box-center DeviceList-Header-box-item1">
            <el-input v-model="searchInput" id="DeviceList-Header-box-center-input" style="width: 240px"
                placeholder="搜索设备..." />
            <el-button type="primary" @click="handleSearch()" :icon="Search"></el-button>
        </div>

        <div class="DeviceList-Header-box-right DeviceList-Header-box-item2">
            <el-button type="primary" :icon="Plus" @click="dialogFormVisible = true">添加设备</el-button>
            <el-button type="primary" :icon="Upload">导出</el-button>
        </div>
    </div>

    <!-- 添加设备弹窗 -->
    <el-dialog 
        v-model="dialogFormVisible" 
        title="添加设备" 
        width="600px" 
        :before-close="closeDialog"
        center>
        <el-form :model="deviceForm" :rules="rules" ref="deviceFormRef" label-width="100px">
            <el-form-item label="设备名称" prop="device_name">
                <el-input v-model="deviceForm.device_name" placeholder="请输入设备名称" />
            </el-form-item>
            
            <el-form-item label="设备类型" prop="type">
                <el-select v-model="deviceForm.type" placeholder="请选择设备类型">
                    <el-option label="路由器" value="路由器" />
                    <el-option label="交换机" value="交换机" />
                    <el-option label="防火墙" value="防火墙" />
                    <el-option label="服务器" value="服务器" />
                </el-select>
            </el-form-item>
            
            <el-form-item label="IPv4地址" prop="ipv4">
                <el-input v-model="deviceForm.ipv4" placeholder="请输入IPv4地址" />
            </el-form-item>

            <el-form-item label="账号" prop="user_name">
                <el-input v-model="deviceForm.user_name" placeholder="请输入账号" />
            </el-form-item>

            <el-form-item label="密码" prop="password">
                <el-input v-model="deviceForm.password" placeholder="请输入密码" />
            </el-form-item>
            
            <el-form-item label="IPv6地址">
                <el-input v-model="deviceForm.ipv6" placeholder="请输入IPv6地址" />
            </el-form-item>
            
            <el-form-item label="MAC地址" prop="mac">
                <el-input v-model="deviceForm.mac" placeholder="请输入MAC地址" />
            </el-form-item>
            
            <el-form-item label="位置" prop="location">
                <el-input v-model="deviceForm.location" placeholder="请输入设备位置" />
            </el-form-item>
            
            <!-- <el-form-item label="状态" prop="status">
                <el-radio-group v-model="deviceForm.status">
                    <el-radio value="在线">在线</el-radio>
                    <el-radio value="离线">离线</el-radio>  
                    <el-radio value="维护中">维护中</el-radio>
                </el-radio-group>
            </el-form-item> -->
        </el-form>
        
        <template #footer>
            <span class="dialog-footer">
                <el-button @click="testConnect()">测试连接</el-button>
                <el-button @click="closeDialog">取消</el-button>
                <el-button type="primary" @click="submitForm">确认</el-button>
            </span>
        </template>
    </el-dialog>
</template>
<script setup>
import { Plus, Upload, Search } from '@element-plus/icons-vue'
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
    // if (deviceFormRef.value) {
    //     deviceFormRef.value.resetFields()
    // }
}

// 提交表单
const submitForm = () => {
    if (!deviceFormRef.value) return
    
    deviceFormRef.value.validate((valid) => {
        if (valid) {
            console.log('提交设备信息:', deviceForm)
            // 这里可以调用API添加设备
            // 添加成功后关闭弹窗
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
.DeviceList-Header-box {
    width: 100%;
    height: 100%;
    display: flex;
    /* 移除 justify-content: space-around */
}

.DeviceList-Header-box div {
    height: 100%;
    display: flex;
    align-items: center;
    /* 移除 width: 100% */
}

.DeviceList-Header-box-item1 {
    flex: 1;
    /* 中间部分占1份 */
    justify-content: center;
    /* 搜索框居中 */
}

.DeviceList-Header-box-item2 {
    flex: 1;
    /* 左右两侧各占1份 */
}

.DeviceList-Header-box-left {
    justify-content: flex-start;
    /* 左侧内容左对齐 */
}

.DeviceList-Header-box-right {
    justify-content: flex-end;
    /* 右侧内容右对齐 */
    padding-right: 0px;
}

.DeviceList-Header-box-right button {
    width: 100px;
    height: 40px;
    margin-left: 10px;
    /* 按钮间距 */
}

.DeviceList-Header-box-center {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    /* 输入框和按钮间距 */
}

.dialog-Header-DeviceList {
    width: 100vw;
    height: 100vh;
    background: rgba(0, 0, 0, 0.7);
    z-index: 100;
    /* opacity: 0.5; */
    position: fixed;
    top: 0;
    left: 0;
    display: flex;
    justify-content: center;
    align-items: center
}

.dialog-box-Header-DeviceList {
    width: 50%;
    height: 50%;
    margin: 0 auto;
    background: #f6f6f6;
    position: fixed;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    opacity: 1;
    z-index: 150;
    padding: 20px;
    border-radius: 10px;
}





</style>