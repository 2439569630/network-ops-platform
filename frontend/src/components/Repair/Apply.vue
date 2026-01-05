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
                <el-form-item label="关联设备 (可选)" prop="device_id">
                  <el-select 
                    v-model="form.device_id" 
                    placeholder="搜索并选择故障设备..." 
                    clearable 
                    filterable
                    remote
                    :remote-method="searchDevices"
                    :loading="deviceLoading"
                    style="width: 100%"
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
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue';
import { 
  Edit, EditPen, Monitor, InfoFilled, WarningFilled, Document, 
  Promotion, Check, CoffeeCup, Timer, Warning, CircleCloseFilled 
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import axios from '@/axios/axios';
import { useRouter } from 'vue-router';

const router = useRouter();
const repairFormRef = ref(null);
const loading = ref(false);
const submitting = ref(false);
const deviceLoading = ref(false);
const deviceOptions = ref([]);

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

const submitForm = async (formEl) => {
  if (!formEl) return;
  await formEl.validate(async (valid, fields) => {
    if (valid) {
      submitting.value = true;
      try {
        const res = await axios.post('/api/v1/repair-orders/', form);
        if (res.data.code === 200) {
          ElMessage.success({
            message: '工单提交成功，我们将尽快处理！',
            type: 'success',
            duration: 3000
          });
          router.push('/user/repair/list'); // 跳转到列表页
        } else {
          ElMessage.error(res.data.message || '提交失败');
        }
      } catch (error) {
        ElMessage.error('提交失败: ' + (error.response?.data?.message || error.message));
      } finally {
        submitting.value = false;
      }
    } else {
      ElMessage.warning('请检查表单填写是否正确');
    }
  });
};

const resetForm = (formEl) => {
  if (!formEl) return;
  formEl.resetFields();
  form.priority = 'medium'; // reset default
};

onMounted(() => {
    initDevices();
});
</script>

<style scoped>
.repair-apply-wrapper {
  padding: 40px 20px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 60px); /* Adjust based on layout */
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
  margin: 0 0 10px 0;
}

.page-subtitle {
  font-size: 14px;
  color: #909399;
  margin: 0;
}

.apply-card {
  border-radius: 8px;
  border: none;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.05) !important;
}

.form-section {
  margin-bottom: 10px;
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
  color: #409eff;
}

/* Priority Selector Styles */
.priority-selector {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 15px;
}

.priority-card {
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  padding: 15px 10px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  transition: all 0.3s;
  position: relative;
  background-color: #fff;
}

.priority-card:hover {
  border-color: #409eff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.05);
}

.priority-card.active {
  border-color: #409eff;
  background-color: #ecf5ff;
}

.priority-card.active .p-label {
  color: #409eff;
  font-weight: bold;
}

/* Specific colors for priorities */
.priority-card.low.active { border-color: #67c23a; background-color: #f0f9eb; }
.priority-card.low.active .p-label, .priority-card.low.active .icon-wrapper { color: #67c23a; }

.priority-card.medium.active { border-color: #e6a23c; background-color: #fdf6ec; }
.priority-card.medium.active .p-label, .priority-card.medium.active .icon-wrapper { color: #e6a23c; }

.priority-card.high.active { border-color: #f56c6c; background-color: #fef0f0; }
.priority-card.high.active .p-label, .priority-card.high.active .icon-wrapper { color: #f56c6c; }

.priority-card.emergency.active { border-color: #8b0000; background-color: #fff0f0; }
.priority-card.emergency.active .p-label, .priority-card.emergency.active .icon-wrapper { color: #8b0000; }


.icon-wrapper {
  font-size: 24px;
  margin-bottom: 8px;
  color: #909399;
  transition: color 0.3s;
}

.text-content .p-label {
  font-size: 14px;
  color: #303133;
  margin-bottom: 4px;
}

.text-content .p-desc {
  font-size: 12px;
  color: #909399;
}

.check-mark {
  position: absolute;
  top: 5px;
  right: 5px;
  color: #409eff;
}

/* Responsive Priority Cards */
@media (max-width: 600px) {
  .priority-selector {
    grid-template-columns: repeat(2, 1fr);
  }
}

.form-actions {
  display: flex;
  justify-content: flex-end;
  gap: 15px;
  margin-top: 30px;
}

.submit-btn {
  padding-left: 30px;
  padding-right: 30px;
}
</style>
