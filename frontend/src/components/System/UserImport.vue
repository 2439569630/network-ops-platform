<template>
  <div class="user-import-page">
    <div class="page-header">
      <div class="header-main">
        <div class="header-title">
          <div class="title">批量导入用户</div>
          <div class="subtitle">上传表格，映射字段并预览后批量创建账号</div>
        </div>
        <div class="header-actions">
          <el-button :icon="Refresh" @click="resetAll" :disabled="loading">重置</el-button>
        </div>
      </div>
    </div>

    <el-card class="main-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div class="card-title">导入流程</div>
          <el-text type="info" size="small">支持 CSV / XLSX，最大 10MB</el-text>
        </div>
      </template>

      <div class="content">
        <div class="section">
          <div class="section-title">1) 上传表格</div>
          <el-upload
            drag
            :show-file-list="false"
            :http-request="uploadAndParse"
            :disabled="loading || loadingCommit"
            accept=".csv,.xlsx"
            class="upload"
          >
            <el-icon class="upload-icon"><UploadFilled /></el-icon>
            <div class="el-upload__text">
              将文件拖到这里，或 <em>点击上传</em>
            </div>
            <template #tip>
              <div class="el-upload__tip">
                表头行作为字段名；建议列名包含：用户名/学号、姓名、邮箱、密码、角色
              </div>
            </template>
          </el-upload>

          <div v-if="loading" class="mt-12">
            <el-alert type="info" show-icon :closable="false" title="正在上传并解析，请稍候" />
            <el-progress
              class="mt-12"
              :percentage="uploadPercent"
              :stroke-width="10"
              :status="uploadPercent >= 100 ? 'success' : undefined"
            />
          </div>

          <el-alert
            v-if="parseMeta"
            type="success"
            show-icon
            :closable="false"
            class="mt-12"
            :title="`已解析：${parseMeta.filename}（共 ${parseMeta.total_rows} 行）`"
          />
        </div>

        <div v-if="parseMeta" class="section">
          <div class="section-title">2) 字段映射</div>
          <el-form label-position="top" class="mapping-form">
            <el-row :gutter="16">
              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="用户名列（必填）">
                  <el-select v-model="mapping.username" filterable clearable placeholder="选择列名">
                    <el-option v-for="c in parseMeta.columns" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="姓名/昵称列（可选）">
                  <el-select v-model="mapping.nickname" filterable clearable placeholder="选择列名">
                    <el-option v-for="c in parseMeta.columns" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="邮箱列（可选）">
                  <el-select v-model="mapping.email" filterable clearable placeholder="选择列名">
                    <el-option v-for="c in parseMeta.columns" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="密码列（可选）">
                  <el-select v-model="mapping.password" filterable clearable placeholder="选择列名">
                    <el-option v-for="c in parseMeta.columns" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="角色列（可选）">
                  <el-select v-model="mapping.role_code" filterable clearable placeholder="选择列名">
                    <el-option v-for="c in parseMeta.columns" :key="c" :label="c" :value="c" />
                  </el-select>
                </el-form-item>
              </el-col>
            </el-row>

            <el-divider content-position="left">默认值</el-divider>

            <el-row :gutter="16">
              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="默认密码（当行内无密码时使用）">
                  <el-input v-model="options.default_password" placeholder="例如：123456" show-password clearable />
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="密码是否已加密">
                  <el-switch v-model="options.password_is_hashed" inline-prompt active-text="已加密" inactive-text="明文" />
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="默认角色（当行内无角色或角色不存在时使用）">
                  <el-select v-model="options.default_role_code" filterable clearable placeholder="选择角色">
                    <el-option v-for="r in roles" :key="r.code" :label="`${r.name} (${r.code})`" :value="r.code" />
                  </el-select>
                </el-form-item>
              </el-col>

              <el-col :xs="24" :sm="12" :md="8">
                <el-form-item label="导入后状态">
                  <el-switch v-model="options.approve_users" inline-prompt active-text="已审核" inactive-text="待审核" />
                </el-form-item>
              </el-col>
            </el-row>

            <div class="actions">
              <el-button type="primary" :icon="Check" :loading="loadingCommit" @click="commitImport">
                开始导入
              </el-button>
              <el-button type="danger" :loading="loadingCancel" :disabled="!canCancel" class="ml-8" @click="cancelImport">
                停止导入
              </el-button>
              <el-text type="info" size="small" class="ml-8">
                重复用户名将跳过（不覆盖）
              </el-text>
            </div>

            <div v-if="loadingCommit || importPercent > 0" class="mt-12">
              <el-alert v-if="loadingCommit" type="info" show-icon :closable="false" title="正在导入，请勿关闭页面" />
              <el-progress
                class="mt-12"
                :percentage="importPercent"
                :stroke-width="10"
                :status="importStatus || undefined"
                :format="formatImportProgress"
              />
              <el-text v-if="importMessage" type="info" size="small" class="mt-8">{{ importMessage }}</el-text>
              <div v-if="importDetail" class="mt-8">
                <el-text type="info" size="small">阶段：{{ phaseText }}</el-text>
                <el-text type="info" size="small" class="ml-8">进度：{{ importDetail.processed || 0 }}/{{ importDetail.total || 0 }}</el-text>
                <el-text type="info" size="small" class="ml-8">
                  创建/跳过/失败：{{ importDetail.created || 0 }}/{{ importDetail.skipped || 0 }}/{{ importDetail.failed || 0 }}
                </el-text>
                <el-text v-if="elapsedText" type="info" size="small" class="ml-8">耗时：{{ elapsedText }}</el-text>
              </div>
            </div>
          </el-form>
        </div>

        <div v-if="parseMeta" class="section">
          <div class="section-title">3) 预览</div>
          <el-table :data="parseMeta.preview_rows" size="small" stripe class="preview-table">
            <el-table-column
              v-for="c in previewColumns"
              :key="c"
              :prop="c"
              :label="c"
              min-width="140"
              show-overflow-tooltip
            />
          </el-table>
          <el-text v-if="parseMeta.columns.length > previewColumns.length" type="info" size="small" class="mt-8">
            仅展示前 {{ previewColumns.length }} 列用于预览
          </el-text>
        </div>

        <div v-if="commitResult" class="section">
          <div class="section-title">4) 导入结果</div>
          <el-row :gutter="16">
            <el-col :xs="24" :sm="8">
              <el-card shadow="never" class="stat">
                <div class="stat-num">{{ commitResult.created }}</div>
                <div class="stat-label">创建成功</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-card shadow="never" class="stat">
                <div class="stat-num">{{ commitResult.skipped }}</div>
                <div class="stat-label">跳过（重复）</div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="8">
              <el-card shadow="never" class="stat">
                <div class="stat-num">{{ commitResult.failed }}</div>
                <div class="stat-label">失败</div>
              </el-card>
            </el-col>
          </el-row>

          <el-alert
            v-if="(commitResult.errors || []).length"
            type="warning"
            show-icon
            :closable="false"
            class="mt-12"
            title="存在部分失败行，可按行号定位原表格修正后重试"
          />

          <el-table v-if="(commitResult.errors || []).length" :data="commitResult.errors" size="small" stripe class="mt-12">
            <el-table-column prop="row" label="行号" width="90" />
            <el-table-column prop="username" label="用户名" min-width="160" show-overflow-tooltip />
            <el-table-column prop="reason" label="原因" min-width="260" show-overflow-tooltip />
          </el-table>
        </div>

        <el-empty v-if="!parseMeta && !loading" description="请先上传表格文件" :image-size="160" />
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import { Check, Refresh, UploadFilled } from '@element-plus/icons-vue';

const loading = ref(false);
const loadingCommit = ref(false);
const loadingCancel = ref(false);
const uploadPercent = ref(0);
const importPercent = ref(0);
const importStatus = ref('');
const importMessage = ref('');
const importDetail = ref(null);
const importStartedAt = ref(null);
const isMobile = ref(false);
let progressTimer = null;
let commitAbortController = null;
let commitCancelledByUser = false;

const checkMobile = () => {
  isMobile.value = window.innerWidth < 768;
};

const parseMeta = ref(null);
const commitResult = ref(null);

const roles = ref([]);
const mapping = ref({
  username: '',
  nickname: '',
  email: '',
  password: '',
  role_code: '',
});

const options = ref({
  default_password: '',
  default_role_code: '',
  approve_users: true,
  on_duplicate: 'skip',
  password_is_hashed: false,
});

const STORAGE_KEY = 'userImportState:v2';

const safeParseJson = (s) => {
  try {
    return JSON.parse(String(s || ''));
  } catch (e) {
    return null;
  }
};

const persistState = () => {
  try {
    const state = {
      parseMeta: parseMeta.value,
      mapping: mapping.value,
      options: options.value,
      commitResult: commitResult.value,
      progress: {
        percent: importPercent.value,
        status: importStatus.value,
        message: importMessage.value,
        detail: importDetail.value,
        started_at: importStartedAt.value,
      },
    };
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (e) {}
};

const clearPersistedState = () => {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch (e) {}
};

const restoreState = () => {
  const raw = (() => {
    try {
      return sessionStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
  })();
  const state = safeParseJson(raw);
  if (!state) return;
  if (state.parseMeta?.token) parseMeta.value = state.parseMeta;
  if (state.mapping) mapping.value = state.mapping;
  if (state.options) options.value = { ...options.value, ...state.options };
  if (state.commitResult) commitResult.value = state.commitResult;
  const p = state.progress || {};
  if (typeof p.percent === 'number') importPercent.value = p.percent;
  if (typeof p.status === 'string') importStatus.value = p.status;
  if (typeof p.message === 'string') importMessage.value = p.message;
  if (p.detail) importDetail.value = p.detail;
  if (p.started_at) importStartedAt.value = p.started_at;
};

const previewColumns = computed(() => {
  const cols = parseMeta.value?.columns || [];
  return cols.slice(0, 8);
});

const canCancel = computed(() => {
  const token = parseMeta.value?.token;
  if (!token) return false;
  if (loadingCancel.value) return false;
  if (loadingCommit.value) return true;
  const st = String(importStatus.value || '').toLowerCase();
  if (st === 'success' || st === 'exception') return false;
  return importPercent.value > 0 && importPercent.value < 100;
});

const phaseText = computed(() => {
  const p = String(importDetail.value?.phase || '').toLowerCase();
  if (p === 'ready') return '就绪';
  if (p === 'prepare') return '准备';
  if (p === 'load_roles') return '读取角色';
  if (p === 'validate') return '校验数据';
  if (p === 'check_existing') return '检查重复';
  if (p === 'hash_passwords') return '生成密码';
  if (p === 'db_insert') return '写入数据';
  if (p === 'bind_roles') return '绑定角色';
  if (p === 'done') return '完成';
  if (p === 'canceled' || p === 'cancelled') return '已停止';
  if (p === 'error') return '错误';
  return p || '-';
});

const elapsedText = computed(() => {
  if (!importStartedAt.value) return '';
  const start = new Date(importStartedAt.value).getTime();
  if (!Number.isFinite(start)) return '';
  const diff = Date.now() - start;
  if (!Number.isFinite(diff) || diff < 0) return '';
  const sec = Math.floor(diff / 1000);
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  if (m <= 0) return `${s}s`;
  return `${m}m${String(s).padStart(2, '0')}s`;
});

const formatImportProgress = (pct) => {
  const t = importDetail.value?.total;
  const d = importDetail.value?.processed;
  if (Number.isFinite(Number(t)) && Number.isFinite(Number(d)) && Number(t) > 0) {
    return `${pct}%（${Number(d)}/${Number(t)}）`;
  }
  return `${pct}%`;
};

const pickColumn = (columns, candidates) => {
  const cols = (columns || []).map(c => String(c || ''));
  const lower = cols.map(c => c.toLowerCase());
  for (const k of candidates) {
    const key = String(k).toLowerCase();
    const idx = lower.findIndex(c => c === key);
    if (idx !== -1) return cols[idx];
  }
  for (const k of candidates) {
    const key = String(k).toLowerCase();
    const idx = lower.findIndex(c => c.includes(key));
    if (idx !== -1) return cols[idx];
  }
  return '';
};

const applyAutoMapping = (columns) => {
  mapping.value.username = pickColumn(columns, ['username', '账号', '学号', '工号', '用户', '用户名', 'user']);
  mapping.value.nickname = pickColumn(columns, ['nickname', '姓名', '名字', '昵称', 'name']);
  mapping.value.email = pickColumn(columns, ['email', '邮箱', '邮件']);
  mapping.value.password = pickColumn(columns, ['password', '密码', '初始密码']);
  mapping.value.role_code = pickColumn(columns, ['role', 'role_code', '角色', '角色编码']);
};

const fetchRoles = async () => {
  try {
    const res = await axios.get('/api/v1/rbac/roles');
    if (res.data?.code === 200) {
      roles.value = Array.isArray(res.data.data) ? res.data.data : [];
      const defaultRole = roles.value.find(r => r?.is_default);
      if (defaultRole?.code && !options.value.default_role_code) {
        options.value.default_role_code = String(defaultRole.code);
      }
    }
  } catch (e) {
    roles.value = [];
  }
};

onMounted(async () => {
  checkMobile();
  window.addEventListener('resize', checkMobile);
  restoreState();
  await fetchRoles();
  await refreshProgressFromServer({ allowResultFetch: true });
});

const stopProgressPolling = () => {
  if (progressTimer) {
    clearInterval(progressTimer);
    progressTimer = null;
  }
};

const startProgressPolling = () => {
  stopProgressPolling();
  progressTimer = setInterval(() => {
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden') return;
    fetchImportProgress();
  }, 1200);
};

onBeforeUnmount(() => {
  window.removeEventListener('resize', checkMobile);
  stopProgressPolling();
});

const fetchImportProgress = async () => {
  const token = parseMeta.value?.token;
  if (!token) return;
  try {
    const res = await axios.get('/api/v1/users/import/progress', { params: { token } });
    if (res.data?.code === 200 && res.data?.data) {
      const d = res.data.data || {};
      const pct = Number(d.percent);
      if (!Number.isNaN(pct)) importPercent.value = Math.max(0, Math.min(100, Math.round(pct)));
      importMessage.value = String(d.message || '');
      importDetail.value = d.detail || null;
      const st = String(d.status || '').toLowerCase();
      if (st === 'done') importStatus.value = 'success';
      else if (st === 'error') importStatus.value = 'exception';
      else if (st === 'canceled' || st === 'cancelled') importStatus.value = 'warning';
      else importStatus.value = '';
      persistState();
      if (st === 'done' || st === 'error' || st === 'canceled' || st === 'cancelled') {
        stopProgressPolling();
      }
    }
  } catch (e) {}
};

const refreshProgressFromServer = async ({ allowResultFetch } = {}) => {
  await fetchImportProgress();
  if (!allowResultFetch) return;
  const token = parseMeta.value?.token;
  if (!token) return;
  const st = String(importDetail.value?.phase || '').toLowerCase();
  if (st !== 'done' && st !== 'canceled' && st !== 'cancelled' && String(importStatus.value || '').toLowerCase() !== 'exception') return;
  if (commitResult.value) return;
  try {
    const res = await axios.get('/api/v1/users/import/result', { params: { token } });
    if (res.data?.code === 200 && res.data?.data) {
      commitResult.value = res.data.data;
      persistState();
    }
  } catch (e) {}
};

const uploadAndParse = async (options) => {
  const file = options?.file;
  if (!file) return;
  loading.value = true;
  commitResult.value = null;
  uploadPercent.value = 0;
  importPercent.value = 0;
  importStatus.value = '';
  importMessage.value = '';
  stopProgressPolling();
  try {
    const form = new FormData();
    form.append('file', file);
    const res = await axios.post('/api/v1/users/import/parse', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (evt) => {
        const total = Number(evt?.total || 0);
        const loaded = Number(evt?.loaded || 0);
        if (total > 0) {
          uploadPercent.value = Math.max(0, Math.min(99, Math.round((loaded * 100) / total)));
        }
      },
    });
    if (res.data?.code === 200 && res.data?.data) {
      parseMeta.value = res.data.data;
      applyAutoMapping(parseMeta.value.columns || []);
      uploadPercent.value = 100;
      importStatus.value = '';
      importMessage.value = '';
      importDetail.value = null;
      importStartedAt.value = null;
      persistState();
      ElMessage.success('解析成功');
    } else {
      ElMessage.error(res.data?.message || '解析失败');
      parseMeta.value = null;
      clearPersistedState();
    }
  } catch (e) {
    ElMessage.error('解析失败');
    parseMeta.value = null;
    clearPersistedState();
  } finally {
    loading.value = false;
  }
};

const commitImport = async () => {
  if (!parseMeta.value?.token) return;
  if (!mapping.value.username) {
    ElMessage.warning('请选择“用户名列”');
    return;
  }
  if (!mapping.value.password && !String(options.value.default_password || '').trim()) {
    ElMessage.warning('未映射密码列且未设置默认密码');
    return;
  }
  loadingCommit.value = true;
  commitCancelledByUser = false;
  importPercent.value = 0;
  importStatus.value = '';
  importMessage.value = '正在启动导入...';
  importDetail.value = null;
  importStartedAt.value = new Date().toISOString();
  persistState();
  stopProgressPolling();
  startProgressPolling();
  await fetchImportProgress();
  try {
    const payload = {
      token: parseMeta.value.token,
      mapping: {
        username: mapping.value.username || null,
        nickname: mapping.value.nickname || null,
        email: mapping.value.email || null,
        password: mapping.value.password || null,
        role_code: mapping.value.role_code || null,
      },
      options: {
        default_password: String(options.value.default_password || '').trim() || null,
        default_role_code: String(options.value.default_role_code || '').trim() || null,
        approve_users: Boolean(options.value.approve_users),
        on_duplicate: 'skip',
        password_is_hashed: Boolean(options.value.password_is_hashed),
      },
    };
    commitAbortController = new AbortController();
    const res = await axios.post('/api/v1/users/import/commit', payload, { signal: commitAbortController.signal });
    if (res.data?.code === 200 && res.data?.data) {
      commitResult.value = res.data.data;
      persistState();
      await refreshProgressFromServer({ allowResultFetch: false });
      if (importStatus.value === 'warning') ElMessage.warning(res.data?.message || '导入已停止');
      else ElMessage.success(res.data?.message || '导入完成');
    } else {
      importStatus.value = 'exception';
      importMessage.value = res.data?.message || '导入失败';
      persistState();
      ElMessage.error(res.data?.message || '导入失败');
    }
  } catch (e) {
    if (commitCancelledByUser || e?.code === 'ERR_CANCELED' || e?.name === 'CanceledError' || e?.name === 'AbortError') {
      importStatus.value = 'warning';
      importMessage.value = '已请求停止导入';
      persistState();
      return;
    }
    importStatus.value = 'exception';
    importMessage.value = '导入失败';
    persistState();
    ElMessage.error('导入失败');
  } finally {
    loadingCommit.value = false;
    commitAbortController = null;
    stopProgressPolling();
    await refreshProgressFromServer({ allowResultFetch: true });
  }
};

const cancelImport = async () => {
  const token = parseMeta.value?.token;
  if (!token) return;
  loadingCancel.value = true;
  commitCancelledByUser = true;
  if (commitAbortController) {
    try {
      commitAbortController.abort();
    } catch (e) {}
    commitAbortController = null;
  }
  loadingCommit.value = false;
  try {
    const res = await axios.post('/api/v1/users/import/cancel', { token });
    if (res.data?.code === 200) {
      ElMessage.success(res.data?.message || '已请求停止导入');
    } else {
      ElMessage.error(res.data?.message || '停止失败');
    }
  } catch (e) {
    ElMessage.error('停止失败');
  } finally {
    loadingCancel.value = false;
    stopProgressPolling();
    await refreshProgressFromServer({ allowResultFetch: true });
  }
};

const resetAll = () => {
  stopProgressPolling();
  parseMeta.value = null;
  commitResult.value = null;
  mapping.value = { username: '', nickname: '', email: '', password: '', role_code: '' };
  options.value = {
    default_password: '',
    default_role_code: options.value.default_role_code || '',
    approve_users: true,
    on_duplicate: 'skip',
    password_is_hashed: false,
  };
  uploadPercent.value = 0;
  importPercent.value = 0;
  importStatus.value = '';
  importMessage.value = '';
  importDetail.value = null;
  importStartedAt.value = null;
  clearPersistedState();
};
</script>

<style scoped>
.user-import-page {
  padding: 18px;
}

.page-header {
  margin-bottom: 14px;
}

.header-main {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 16px;
}

.header-title .title {
  font-size: 18px;
  font-weight: 600;
}

.header-title .subtitle {
  margin-top: 4px;
  color: #6b7280;
  font-size: 13px;
}

.main-card {
  border-radius: 12px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-title {
  font-weight: 600;
}

.content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.section-title {
  font-weight: 600;
  margin-bottom: 10px;
}

.upload {
  width: 100%;
}

.upload-icon {
  font-size: 28px;
  color: #409eff;
  margin-bottom: 6px;
}

.actions {
  display: flex;
  align-items: center;
  margin-top: 8px;
  flex-wrap: wrap;
  gap: 8px;
}

.stat {
  border-radius: 12px;
  margin-bottom: 8px;
}

.stat-num {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
}

.stat-label {
  margin-top: 6px;
  color: #6b7280;
  font-size: 13px;
}

.mt-8 {
  margin-top: 8px;
}

.mt-12 {
  margin-top: 12px;
}

.ml-8 {
  margin-left: 8px;
}

/* Mobile Responsive */
@media (max-width: 768px) {
  .user-import-page {
    padding: 12px;
  }
  
  .header-main {
    flex-direction: column;
    align-items: flex-start;
  }
  
  .header-actions {
    width: 100%;
    display: flex;
    justify-content: flex-end;
  }
  
  .actions {
    flex-direction: column;
    align-items: stretch;
  }
  
  .actions .el-button {
    margin-left: 0 !important;
    width: 100%;
  }
  
  .actions .el-text {
    margin-left: 0 !important;
    margin-top: 8px;
    text-align: center;
  }
  
  .preview-table {
    overflow-x: auto;
  }
}
</style>
