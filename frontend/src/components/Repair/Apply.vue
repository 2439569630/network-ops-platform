<template>
  <div class="repair-apply-wrapper" :class="{ 'is-mobile': isMobile }">
    <div class="apply-content">
      <!-- Header Section -->
      <div class="apply-header">
        <h1 class="page-title">故障报修</h1>
        <p class="page-subtitle">请填写以下信息提交工单，我们将尽快为您处理</p>
      </div>

      <!-- Main Form Card -->
      <el-card class="apply-card" :shadow="isMobile ? 'never' : 'hover'">
        <el-form 
          ref="repairFormRef" 
          :model="form" 
          :rules="rules" 
          :label-position="isMobile ? 'top' : 'top'"
          class="repair-form"
          v-loading="loading"
          :size="isMobile ? 'default' : 'large'"
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
                <el-form-item prop="location_id" label="报修位置">
                  <div class="location-input-group">
                    <el-cascader
                      v-model="form.location_id"
                      :options="locationOptions"
                      :props="{ value: 'id', label: 'label', children: 'children', checkStrictly: true, emitPath: false }"
                      placeholder="请选择故障位置"
                      clearable
                      filterable
                      class="location-select"
                      :size="isMobile ? 'default' : 'large'"
                      v-loading="locationLoading"
                      :show-all-levels="false"
                    >
                      <template #prefix>
                        <el-icon><Location /></el-icon>
                      </template>
                    </el-cascader>
                  </div>
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
                :rows="isMobile ? 4 : 6" 
                placeholder="请详细描述故障现象、复现步骤、报错信息等..." 
                resize="none"
              />
            </el-form-item>
          </div>

          <el-divider />

          <!-- 4. Images -->
          <div class="form-section">
            <h3 class="section-title"><el-icon><Picture /></el-icon> 现场图片（可选）</h3>
            <el-form-item>
              <el-upload
                v-model:file-list="orderImageFileList"
                list-type="picture-card"
                :before-upload="beforeOrderImageSelect"
                :auto-upload="false"
                :on-change="handleOrderImageChange"
                :limit="6"
                accept="image/*"
              >
                <el-icon><Plus /></el-icon>
              </el-upload>
              <div class="el-upload__tip">最多上传 6 张图片，单张图片最大 5MB。</div>
            </el-form-item>
          </div>

          <!-- Actions -->
          <div class="form-actions" :class="{ 'fixed-footer': isMobile }">
            <el-button @click="resetForm(repairFormRef)" :size="isMobile ? 'default' : 'large'" v-if="!isMobile">重置</el-button>
            <el-button 
              type="primary" 
              @click="submitForm(repairFormRef)" 
              :loading="submitting"
              :size="isMobile ? 'large' : 'large'"
              class="submit-btn"
              :block="isMobile"
            >
              提交工单 <el-icon class="el-icon--right"><Promotion /></el-icon>
            </el-button>
          </div>
          <!-- Mobile Spacer -->
          <div v-if="isMobile" style="height: 60px;"></div>
        </el-form>
      </el-card>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue';
import { 
  Edit, EditPen, Monitor, InfoFilled, WarningFilled, Document, 
  Promotion, Check, CoffeeCup, Timer, Warning, CircleCloseFilled,
  Location, Picture, Plus
} from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import axios from '@/axios/axios';
import { useRouter } from 'vue-router';

const router = useRouter();
const repairFormRef = ref(null);
const loading = ref(false);
const locationLoading = ref(false);
const submitting = ref(false);
const locationOptions = ref([]);

const isMobile = ref(window.innerWidth < 768)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }

const form = reactive({
  title: '',
  location_id: null,
  priority: 'medium',
  description: ''
});

const orderImageFileList = ref([]);

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

// 获取位置树
const fetchLocations = async () => {
    locationLoading.value = true;
    try {
        const res = await axios.get('/api/v1/locations/tree');
        if (res.data && res.data.code === 200) {
            locationOptions.value = res.data.data;
        }
    } catch (error) {
        console.error("Location fetch error", error);
    } finally {
        locationLoading.value = false;
    }
};

const resetForm = (formEl) => {
  if (!formEl) return;
  formEl.resetFields();
  form.priority = 'medium';
  form.location_id = null;
  orderImageFileList.value = [];
};

const beforeOrderImageSelect = (file) => {
  const type = String(file?.type || '');
  if (!type.startsWith('image/')) {
    ElMessage.error('仅支持图片文件');
    return false;
  }
  const maxBytes = 5 * 1024 * 1024;
  const size = Number(file?.size || 0);
  if (size > maxBytes) {
    ElMessage.error('图片过大(最大 5MB)');
    return false;
  }
  return true;
};

const handleOrderImageChange = (file, fileList) => {
  const raw = file?.raw;
  if (!raw) {
    ElMessage.error('图片读取失败，请重新选择');
    orderImageFileList.value = (fileList || []).filter((x) => x?.uid !== file?.uid);
    return;
  }
  const type = String(raw?.type || '');
  if (!type.startsWith('image/')) {
    ElMessage.error('仅支持图片文件');
    orderImageFileList.value = (fileList || []).filter((x) => x?.uid !== file?.uid);
    return;
  }
  const maxBytes = 5 * 1024 * 1024;
  const size = Number(raw?.size || 0);
  if (size > maxBytes) {
    ElMessage.error('图片过大(最大 5MB)');
    orderImageFileList.value = (fileList || []).filter((x) => x?.uid !== file?.uid);
    return;
  }
  orderImageFileList.value = fileList || [];
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
          location_id: form.location_id
        };
        const res = await axios.post('/api/v1/repair-orders/', payload);
        if (res.data && res.data.code === 200) {
          const id = res.data?.data?.id;
          const files = Array.isArray(orderImageFileList.value) ? orderImageFileList.value : [];
          let uploaded = 0;
          let failed = 0;
          const maxBytes = 5 * 1024 * 1024;
          for (const f of files) {
            const raw = f?.raw;
            if (!raw) {
              failed += 1;
              ElMessage.error('图片读取失败，请重新选择');
              continue;
            }
            const type = String(raw?.type || '');
            if (!type.startsWith('image/')) {
              failed += 1;
              ElMessage.error('仅支持图片文件');
              continue;
            }
            const size = Number(raw?.size || 0);
            if (size > maxBytes) {
              failed += 1;
              ElMessage.error('图片过大(最大 5MB)');
              continue;
            }
            const formData = new FormData();
            formData.append('file', raw);
            if (id) formData.append('order_id', String(id));
            try {
              const up = await axios.post('/api/v1/repair-images/upload', formData, {
                headers: { 'Content-Type': 'multipart/form-data' }
              });
              if (up.data?.code === 200) uploaded += 1;
              else {
                failed += 1;
                ElMessage.error(up.data?.message || '图片上传失败');
              }
            } catch (e) {
              failed += 1;
              ElMessage.error(e?.response?.data?.message || '图片上传失败');
            }
          }
          if (uploaded > 0 && failed === 0) ElMessage.success(`报修单提交成功，已上传 ${uploaded} 张图片`);
          else if (uploaded > 0 && failed > 0) ElMessage.warning(`报修单提交成功，成功上传 ${uploaded} 张，失败 ${failed} 张`);
          else ElMessage.success('报修单提交成功');
          router.push('/user/repair/list');
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

onMounted(() => {
    window.addEventListener('resize', checkMobile)
    fetchLocations();
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile)
})
</script>

<style scoped>
.repair-apply-wrapper {
  padding: 40px 20px;
  min-height: 100%;
  background-color: #f5f7fa;
  display: flex;
  justify-content: center;
}

.repair-apply-wrapper.is-mobile {
  padding: 0;
  display: block;
  background-color: #fff;
}

.apply-content {
  width: 100%;
  max-width: 800px;
}

.apply-header {
  text-align: center;
  margin-bottom: 30px;
}

.is-mobile .apply-header {
  margin-bottom: 20px;
  padding: 16px 16px 0 16px;
  text-align: left;
}

.page-title {
  font-size: 28px;
  font-weight: 600;
  color: #303133;
  margin: 0 0 8px 0;
}

.is-mobile .page-title {
  font-size: 24px;
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

.is-mobile .apply-card {
  box-shadow: none !important;
  border-radius: 0;
}

.repair-form {
  padding: 10px;
}

.is-mobile .repair-form {
  padding: 0 16px;
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

.is-mobile .priority-selector {
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
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

.form-actions.fixed-footer {
  position: fixed;
  bottom: 0;
  left: 0;
  width: 100%;
  background: #fff;
  padding: 12px 16px;
  box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
  z-index: 100;
  margin-top: 0;
}

.submit-btn {
  padding-left: 32px;
  padding-right: 32px;
  font-weight: 500;
}

.fixed-footer .submit-btn {
  width: 100%;
}

.location-input-group {
    display: flex;
    gap: 8px;
    width: 100%;
}
.location-select {
    flex: 1;
    min-width: 0; /* 防止 flex item 溢出 */
}

.form-tip {
    font-size: 12px;
    color: #909399;
    margin-top: 4px;
    line-height: 1.4;
}
</style>
