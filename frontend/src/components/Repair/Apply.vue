<template>
  <div class="repair-apply-wrapper">
    <div class="apply-content">
      <!-- Header Section -->
      <div class="apply-header">
        <h1 class="page-title">故障报修</h1>
        <p class="page-subtitle">请填写以下信息提交工单，我们将尽快为您处理</p>
      </div>

      <!-- Main Form Card -->
      <el-card class="apply-card" shadow="hover">
        <el-form 
          ref="repairFormRef" 
          :model="form" 
          :rules="rules" 
          label-position="top"
          class="repair-form"
          v-loading="loading"
          size="large"
        >
          <!-- 1. Basic Info -->
          <div class="form-section">
            <h3 class="section-title"><el-icon><InfoFilled /></el-icon> 基本信息</h3>
            
            <el-row :gutter="24">
              <el-col :span="24">
                <el-form-item label="故障标题" prop="title">
                  <el-input 
                    v-model="form.title" 
                    placeholder="例如：主楼 302 交换机无法连接" 
                    prefix-icon="Edit"
                    maxlength="50"
                    show-word-limit
                  />
                </el-form-item>
              </el-col>
            </el-row>

            <el-row :gutter="24">
              <el-col :span="24">
                <el-form-item prop="device_id" label="关联设备 (可选)">
                  <div class="device-input-group">
                    <el-select 
                      v-model="form.device_id" 
                      placeholder="搜索设备..." 
                      clearable 
                      filterable
                      remote
                      :remote-method="searchDevices"
                      :loading="deviceLoading"
                      class="device-select"
                      size="large"
                    >
                      <template #prefix>
                        <el-icon><Monitor /></el-icon>
                      </template>
                      <el-option
                        v-for="item in deviceOptions"
                        :key="item.id"
                        :label="item.device_name"
                        :value="item.id"
                      >
                        <span style="float: left">{{ item.device_name }}</span>
                        <span style="float: right; color: var(--el-text-color-secondary); font-size: 13px">
                          {{ item.ipv4 }}
                        </span>
                      </el-option>
                    </el-select>
                    <el-button 
                        type="primary" 
                        size="large" 
                        :icon="Scan" 
                        class="scan-btn-inline" 
                        @click="startScan"
                        plain
                    >
                        扫码
                    </el-button>
                  </div>
                  <div class="form-tip">支持扫描设备标签上的二维码快速关联</div>
                </el-form-item>
              </el-col>
            </el-row>
          </div>

          <el-divider />

          <!-- 2. Priority -->
          <div class="form-section">
            <h3 class="section-title"><el-icon><WarningFilled /></el-icon> 紧急程度</h3>
            <el-form-item prop="priority">
              <div class="priority-selector">
                <div 
                  v-for="p in priorityOptions" 
                  :key="p.value"
                  class="priority-card"
                  :class="{ active: form.priority === p.value, [p.value]: true }"
                  @click="form.priority = p.value"
                >
                  <div class="icon-wrapper">
                    <el-icon><component :is="p.icon" /></el-icon>
                  </div>
                  <div class="text-content">
                    <div class="p-label">{{ p.label }}</div>
                    <div class="p-desc">{{ p.desc }}</div>
                  </div>
                  <div class="check-mark" v-if="form.priority === p.value">
                    <el-icon><Check /></el-icon>
                  </div>
                </div>
              </div>
            </el-form-item>
          </div>

          <el-divider />

          <!-- 3. Description -->
          <div class="form-section">
            <h3 class="section-title"><el-icon><Document /></el-icon> 详细描述</h3>
            <el-form-item prop="description">
              <el-input 
                v-model="form.description" 
                type="textarea" 
                :rows="6" 
                placeholder="请详细描述故障现象、复现步骤、报错信息等..." 
                resize="none"
              />
            </el-form-item>
          </div>

          <!-- Actions -->
          <div class="form-actions">
            <el-button @click="resetForm(repairFormRef)" size="large">重置</el-button>
            <el-button 
              type="primary" 
              @click="submitForm(repairFormRef)" 
              :loading="submitting"
              size="large"
              class="submit-btn"
            >
              提交工单 <el-icon class="el-icon--right"><Promotion /></el-icon>
            </el-button>
          </div>
        </el-form>
      </el-card>
    </div>

    <!-- Scan Dialog -->
    <el-dialog
        v-model="scanDialogVisible"
        title="扫描设备二维码"
        width="500px"
        :before-close="handleScanClose"
        append-to-body
        align-center
    >
        <div class="scan-container">
            <div id="reader" class="qr-reader"></div>
            <p class="scan-tip">请将摄像头对准设备二维码</p>
        </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue';
import { 
  Edit, EditPen, Monitor, InfoFilled, WarningFilled, Document, 
  Promotion, Check, CoffeeCup, Timer, Warning, CircleCloseFilled,
  FullScreen as Scan 
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import axios from '@/axios/axios';
import { useRouter } from 'vue-router';
import { Html5Qrcode } from "html5-qrcode";

const router = useRouter();
const repairFormRef = ref(null);
const loading = ref(false);
const submitting = ref(false);
const deviceLoading = ref(false);
const deviceOptions = ref([]);

// Scan
const scanDialogVisible = ref(false);
let html5QrCode = null;

const form = reactive({
  title: '',
  device_id: null,
  priority: 'medium',
  description: ''
});

const priorityOptions = [
  { value: 'low', label: '低', desc: '不影响使用', icon: 'CoffeeCup' },
  { value: 'medium', label: '中', desc: '局部受影响', icon: 'Timer' },
  { value: 'high', label: '高', desc: '功能受损', icon: 'Warning' },
  { value: 'emergency', label: '紧急', desc: '系统瘫痪', icon: 'CircleCloseFilled' }
];

const rules = reactive({
  title: [
    { required: true, message: '请输入故障标题', trigger: 'blur' },
    { min: 5, max: 50, message: '长度在 5 到 50 个字符', trigger: 'blur' }
  ],
  priority: [
    { required: true, message: '请选择紧急程度', trigger: 'change' }
  ],
  description: [
    { required: true, message: '请输入详细描述', trigger: 'blur' },
    { min: 10, message: '描述太短，请至少输入 10 个字符', trigger: 'blur' }
  ]
});

// 搜索设备
const searchDevices = async (query) => {
  if (query) {
    deviceLoading.value = true;
    try {
      // 复用设备列表接口，简单过滤
      const res = await axios.get('/api/v1/user/device/get');
      if (res.data && Array.isArray(res.data)) {
          deviceOptions.value = res.data.filter(item => 
              item.device_name.toLowerCase().includes(query.toLowerCase()) || 
              item.ipv4.includes(query)
          );
      }
    } catch (error) {
      console.error("Device search error", error);
    } finally {
      deviceLoading.value = false;
    }
  } else {
    deviceOptions.value = [];
  }
};

// 初始化加载部分设备
const initDevices = async () => {
    try {
        const res = await axios.get('/api/v1/user/device/get');
        if (res.data && Array.isArray(res.data)) {
            deviceOptions.value = res.data.slice(0, 20); 
        }
    } catch (error) {
        // ignore error
    }
};

const resetForm = (formEl) => {
  if (!formEl) return;
  formEl.resetFields();
  form.priority = 'medium';
  deviceOptions.value = [];
};

const submitForm = async (formEl) => {
  if (!formEl) return;
  await formEl.validate(async (valid, fields) => {
    if (valid) {
      submitting.value = true;
      try {
        const payload = {
          title: form.title,
          description: form.description,
          priority: form.priority,
          device_id: form.device_id
        };
        const res = await axios.post('/api/v1/repair-orders/', payload);
        if (res.data && res.data.code === 200) {
          ElMessage.success('报修单提交成功');
          router.push('/user/repair');
        } else {
          ElMessage.error(res.data.message || '提交失败');
        }
      } catch (error) {
        ElMessage.error('提交失败，请稍后重试');
        console.error(error);
      } finally {
        submitting.value = false;
      }
    } else {
      console.log('Validation failed', fields);
    }
  });
};

// --- Scan Logic ---
const startScan = () => {
  scanDialogVisible.value = true;
  // Wait for dialog animation
  setTimeout(() => {
    if (!html5QrCode) {
      html5QrCode = new Html5Qrcode("reader");
    }
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };
    html5QrCode.start(
      { facingMode: "environment" }, 
      config, 
      onScanSuccess, 
      onScanFailure
    ).catch(err => {
      console.error("Error starting scanner", err);
      ElMessage.error("无法启动摄像头，请检查权限");
    });
  }, 300);
};

const onScanSuccess = (decodedText, decodedResult) => {
  console.log(`Scan result: ${decodedText}`, decodedResult);
  // Expected format: "DeviceID:123" or just "123"
  let id = null;
  if (decodedText.startsWith("DeviceID:")) {
      id = decodedText.split(":")[1];
  } else if (decodedText.startsWith("LocationID:")) {
      // If it's a location, maybe we can't directly bind device, but let's see. 
      // For now, assume device scan.
      ElMessage.warning("扫描到的是位置码，请扫描设备码");
      return; 
  } else if (/^\d+$/.test(decodedText)) {
      id = decodedText;
  }
  
  if (id) {
      handleScanClose();
      form.device_id = Number(id);
      // Optional: Fetch device info to display correct label
      fetchDeviceInfo(id);
      ElMessage.success("扫码成功，已自动关联设备");
  } else {
      ElMessage.warning(`无法识别的二维码格式: ${decodedText}`);
  }
};

const onScanFailure = (error) => {
  // console.warn(`Code scan error = ${error}`);
};

const handleScanClose = () => {
  if (html5QrCode && html5QrCode.isScanning) {
    html5QrCode.stop().then(() => {
        html5QrCode.clear();
        scanDialogVisible.value = false;
    }).catch(err => {
        console.error("Failed to stop scanner", err);
        scanDialogVisible.value = false;
    });
  } else {
      scanDialogVisible.value = false;
  }
};

const fetchDeviceInfo = async (id) => {
    try {
        // API path correction: /detail/{id}
        // Note: The backend returns the device object directly, not wrapped in { code: 200, data: ... }
        const res = await axios.get(`/api/v1/user/device/detail/${id}`);
        const dev = res.data;
        if (dev && dev.id) {
            deviceOptions.value = [dev];
            form.device_id = dev.id;
        } else {
             // In case it is wrapped (defensive)
             if (dev.data && dev.code === 200) {
                 deviceOptions.value = [dev.data];
                 form.device_id = dev.data.id;
             }
        }
    } catch(e) {
        console.error("Fetch device error", e);
        ElMessage.warning("获取设备信息失败，请确认设备ID是否正确");
    }
}

onMounted(() => {
    initDevices();
});

onBeforeUnmount(() => {
    if (html5QrCode && html5QrCode.isScanning) {
        html5QrCode.stop().catch(err => console.error(err));
    }
});
</script>

<style scoped>
.repair-apply-wrapper {
  padding: 40px 20px;
  min-height: 100%;
  background-color: #f5f7fa;
  display: flex;
  justify-content: center;
}

.apply-content {
  width: 100%;
  max-width: 800px;
}

.apply-header {
  text-align: center;
  margin-bottom: 30px;
}

.page-title {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px 0;
}

.page-subtitle {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.apply-card {
  border-radius: 12px;
  border: none;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05) !important;
  background: #ffffff;
}

.repair-form {
  padding: 10px;
}

.form-section {
  margin-bottom: 24px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 20px 0;
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title .el-icon {
  color: var(--el-color-primary);
}

/* Priority Selector */
.priority-selector {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.priority-card {
  position: relative;
  border: 1px solid #e4e7ed;
  border-radius: 12px;
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s ease-in-out;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  background-color: #ffffff;
}

.priority-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}

/* Active State - Solid Colors */
.priority-card.active {
  border-color: transparent;
  color: white;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
}

/* Low - Green */
.priority-card.low:hover { border-color: #67C23A; }
.priority-card.low.active { background-color: #67C23A; }

/* Medium - Orange */
.priority-card.medium:hover { border-color: #E6A23C; }
.priority-card.medium.active { background-color: #E6A23C; }

/* High - Red */
.priority-card.high:hover { border-color: #F56C6C; }
.priority-card.high.active { background-color: #F56C6C; }

/* Emergency - Dark Red/Purple */
.priority-card.emergency:hover { border-color: #cf1322; }
.priority-card.emergency.active { background-color: #cf1322; }

.icon-wrapper {
  font-size: 28px;
  color: #909399;
  margin-bottom: 12px;
  transition: color 0.2s;
}

.priority-card:hover .icon-wrapper {
  color: #606266;
}

/* Active Icon Colors (White) */
.priority-card.active .icon-wrapper {
  color: #ffffff !important;
}

.text-content .p-label {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
  transition: color 0.2s;
}

.priority-card.active .p-label {
  color: #ffffff;
}

.text-content .p-desc {
  font-size: 12px;
  color: #909399;
  transition: color 0.2s;
}

.priority-card.active .p-desc {
  color: rgba(255, 255, 255, 0.85);
}

.check-mark {
  position: absolute;
  top: 8px;
  right: 8px;
  color: white;
  background: rgba(0,0,0,0.1);
  border-radius: 50%;
  padding: 2px;
  font-size: 12px;
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 16px;
  margin-top: 32px;
}

.submit-btn {
  padding-left: 32px;
  padding-right: 32px;
  font-weight: 500;
}

.device-input-group {
    display: flex;
    gap: 8px;
    width: 100%;
}
.device-select {
    flex: 1;
    min-width: 0; /* 防止 flex item 溢出 */
}
.scan-btn-inline {
    padding: 0 16px;
    flex-shrink: 0;
}

.form-tip {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
    line-height: 1.4;
}

.scan-container {
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px;
}
.qr-reader {
    width: 100%;
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 2px 12px rgba(0,0,0,0.1);
}
.scan-tip {
    margin-top: 20px;
    color: #606266;
    font-size: 15px;
    font-weight: 500;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .repair-apply-wrapper {
    padding: 0; /* 全宽 */
    background-color: #f5f7fa;
    display: block; /* 覆盖 flex */
  }
  
  .apply-content {
      max-width: 100%;
  }

  .apply-header {
      padding: 24px 20px 0 20px;
      margin-bottom: 20px;
      text-align: left;
  }
  
  .page-title {
      font-size: 24px;
  }
  
  .page-subtitle {
      font-size: 13px;
  }

  .apply-card {
      border-radius: 20px 20px 0 0; /* 顶部圆角 */
      box-shadow: none !important;
      margin-bottom: 0;
      min-height: calc(100vh - 100px); /* 确保内容区填满 */
  }

  .repair-form {
      padding: 10px 16px 40px 16px; /* 底部留白，增加左右内边距 */
  }

  .form-section {
      margin-bottom: 20px;
  }

  /* Priority Selector 2 columns on mobile */
  .priority-selector {
    grid-template-columns: repeat(2, 1fr);
    gap: 12px;
  }
  
  .priority-card {
      padding: 12px;
      border-radius: 10px;
  }
  
  .icon-wrapper {
      font-size: 24px;
      margin-bottom: 6px;
  }
  
  .text-content .p-label {
      font-size: 14px;
  }
  
  .text-content .p-desc {
      font-size: 11px;
  }
  
  /* Scan Button Mobile Optimization */
  .scan-btn-inline {
      padding: 0 12px; /* 减小内边距 */
  }
  .scan-btn-inline span {
      display: none; /* 隐藏文字，只显示图标 */
  }
  
  /* Buttons */
  .form-actions {
      flex-direction: column-reverse; /* 提交按钮在上方 */
      gap: 12px;
  }
  
  .submit-btn, .form-actions .el-button {
      width: 100%;
      margin-left: 0 !important;
  }
}
</style>
