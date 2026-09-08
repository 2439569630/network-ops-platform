<template>
  <div class="org-management">
    <el-card class="box-card" shadow="never">
      <!-- Header Actions -->
      <template #header>
        <div class="card-header">
          <div class="left-actions">
            <span class="title">组织架构管理</span>
          </div>
          <div class="right-actions">
            <el-button-group>
                <el-button :icon="Plus" type="primary" @click="handleAddRoot">新建根节点</el-button>
                <el-button :icon="Download" @click="handleExport">导出数据</el-button>
                <el-button :icon="Refresh" @click="handleRefresh">刷新</el-button>
                <el-button :icon="Sort" @click="toggleExpandAll">{{ isExpandAll ? '折叠全部' : '展开全部' }}</el-button>
            </el-button-group>
          </div>
        </div>
      </template>

      <!-- Filter -->
      <div class="filter-container">
         <el-input 
            v-model="filterText" 
            placeholder="搜索组织/部门/负责人" 
            :prefix-icon="Search" 
            clearable 
            style="max-width: 400px"
         />
      </div>

      <!-- Tree -->
      <div class="tree-container" v-loading="loading">
        <el-tree
          ref="treeRef"
          :data="orgData"
          :props="defaultProps"
          :filter-node-method="filterNode"
          node-key="id"
          :default-expand-all="isExpandAll"
          draggable
          :allow-drop="allowDrop"
          :allow-drag="allowDrag"
          @node-drop="handleDrop"
          highlight-current
          :expand-on-click-node="false"
        >
          <template #default="{ node, data }">
            <div class="custom-tree-node" :class="{ 'is-disabled': data.status === false }">
              <div class="node-content">
                  <!-- Icon & Label -->
                  <span class="node-main">
                      <el-icon :color="getTypeColor(data.type)" class="node-icon">
                          <component :is="getTypeIcon(data.type)" />
                      </el-icon>
                      <span class="node-label">
                        <template v-for="(p, idx) in highlightParts(node.label)" :key="idx">
                          <span v-if="p.highlight" class="node-highlight">{{ p.text }}</span>
                          <span v-else>{{ p.text }}</span>
                        </template>
                      </span>
                      
                      <el-tag size="small" :type="getTypeTagEffect(data.type)" effect="plain" class="ml-2 tag-type">
                        {{ getTypeName(data.type) }}
                      </el-tag>
                       <el-tag v-if="data.status === false" size="small" type="danger" effect="dark" class="ml-2">已禁用</el-tag>
                  </span>
                  
                  <!-- Info (Hide on small screens via CSS) -->
                  <span class="node-info">
                      <span class="info-item" v-if="data.manager" title="负责人">
                          <el-icon><User /></el-icon> {{ data.manager }}
                      </span>
                      <span class="info-item code-item" v-if="data.code" title="编码">
                          #{{ data.code }}
                      </span>
                  </span>
              </div>

              <!-- Actions -->
              <div class="node-actions">
                  <el-tooltip content="添加下级" placement="top" :show-after="500">
                    <el-button link type="primary" :icon="Plus" @click.stop="append(data)"></el-button>
                  </el-tooltip>
                  <el-tooltip content="编辑" placement="top" :show-after="500">
                    <el-button link type="warning" :icon="Edit" @click.stop="handleEdit(data)"></el-button>
                  </el-tooltip>
                  <el-tooltip content="删除" placement="top" :show-after="500">
                    <el-button link type="danger" :icon="Delete" @click.stop="remove(node, data)"></el-button>
                  </el-tooltip>
              </div>
            </div>
          </template>
        </el-tree>
        
        <el-empty v-if="!orgData || orgData.length === 0" description="暂无组织架构数据" />
      </div>
    </el-card>

    <!-- Edit/Create Dialog -->
    <el-dialog 
        v-model="dialogVisible" 
        :title="dialogTitle" 
        width="500px"
        :close-on-click-modal="false"
        destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
        <el-row :gutter="20">
            <el-col :span="24">
                <el-form-item label="名称" prop="label">
                  <el-input v-model="form.label" placeholder="请输入组织名称" maxlength="50" show-word-limit />
                </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="类型" prop="type">
                  <el-select v-model="form.type" placeholder="请选择类型" :disabled="formType === 'edit' && form.type === 'school'">
                    <el-option label="学校" value="school" v-if="isRoot || form.type === 'school'" />
                    <el-option label="学院/直属单位" value="college" />
                    <el-option label="系/部门" value="department" />
                    <el-option label="实验室/办公室" value="office" />
                  </el-select>
                </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="编码" prop="code">
                    <el-input v-model="form.code" placeholder="如: CS001" />
                 </el-form-item>
            </el-col>
            <el-col :span="24">
                <el-form-item label="负责人" prop="manager">
                     <el-select 
                        v-model="form.manager" 
                        filterable 
                        placeholder="搜索负责人"
                        style="width: 100%"
                        clearable
                     >
                        <el-option
                            v-for="item in userOptions"
                            :key="item.value"
                            :label="item.label"
                            :value="item.label"
                        >
                            <span style="float: left">{{ item.label }}</span>
                            <span style="float: right; color: var(--el-text-color-secondary); font-size: 13px">{{ item.dept }}</span>
                        </el-option>
                     </el-select>
                </el-form-item>
            </el-col>
            <el-col :span="24">
                <el-form-item label="描述" prop="description">
                    <el-input v-model="form.description" type="textarea" :rows="2" placeholder="请输入描述信息" maxlength="200" show-word-limit />
                </el-form-item>
            </el-col>
            <el-col :span="24">
                 <el-form-item label="状态" prop="status">
                    <el-switch v-model="form.status" active-text="启用" inactive-text="禁用" />
                 </el-form-item>
            </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <span class="dialog-footer">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave" :loading="saving">确定</el-button>
        </span>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, reactive, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
    School, Reading, OfficeBuilding, User, 
    Plus, Edit, Delete, Search, Download, Refresh, Sort 
} from '@element-plus/icons-vue'

// --- State ---
const filterText = ref('')
const treeRef = ref(null)
const loading = ref(false)
const saving = ref(false)
const isExpandAll = ref(true)

// Dialog
const dialogVisible = ref(false)
const dialogTitle = ref('新建节点')
const formType = ref('create') // 'create' | 'edit'
const formRef = ref(null)
const isRoot = ref(false)
const currentParent = ref(null)
const currentEditNode = ref(null)

// Form Data
const form = reactive({
    id: null,
    label: '',
    type: 'department',
    code: '',
    manager: '',
    description: '',
    status: true
})

// Rules
const rules = {
    label: [
        { required: true, message: '请输入名称', trigger: 'blur' },
        { min: 2, max: 50, message: '长度在 2 到 50 个字符', trigger: 'blur' }
    ],
    type: [
        { required: true, message: '请选择类型', trigger: 'change' }
    ]
}

// Mock User Options
const userOptions = [
    { value: '1', label: '张三', dept: '网络运维组' },
    { value: '2', label: '李四', dept: '教务处' },
    { value: '3', label: '王五', dept: '计算机学院' },
    { value: '4', label: '赵六', dept: '系统管理组' },
]

// Tree Data
const defaultProps = {
  children: 'children',
  label: 'label',
}

const orgData = ref([
  {
    id: 1,
    label: '某某大学',
    type: 'school',
    code: 'UNIV001',
    manager: '校长办',
    status: true,
    children: [
      {
        id: 2,
        label: '计算机学院',
        type: 'college',
        code: 'CS',
        manager: '王院长',
        status: true,
        children: [
          {
            id: 4,
            label: '计算机系',
            type: 'department',
            code: 'CS01',
            manager: '张主任',
            status: true,
            children: [{ id: 9, label: '网络实验室', type: 'office', code: 'LAB01', manager: '李老师', status: true }],
          },
          {
            id: 5,
            label: '软件工程系',
            type: 'department',
            code: 'SE01',
            manager: '赵主任',
            status: true,
          },
        ],
      },
      {
        id: 3,
        label: '行政部门',
        type: 'college',
        code: 'ADM',
        manager: '',
        status: true,
        children: [
          {
            id: 6,
            label: '信息化办公室',
            type: 'department',
            code: 'IT',
            manager: '周主任',
            status: true,
            children: [
                { id: 7, label: '网络运维组', type: 'office', code: 'NET', manager: '吴组长', status: true },
                { id: 8, label: '系统管理组', type: 'office', code: 'SYS', manager: '郑组长', status: true }
            ]
          },
        ],
      },
    ],
  },
])

// --- Watchers ---
watch(filterText, (val) => {
  treeRef.value?.filter(val)
})

// --- Methods ---

const filterNode = (value, data) => {
  if (!value) return true
  const lowerValue = String(value || '').toLowerCase()
  return String(data?.label || '').toLowerCase().includes(lowerValue) || 
         String(data?.manager || '').toLowerCase().includes(lowerValue)
}

const highlightParts = (text) => {
  const source = String(text ?? '')
  const keyword = String(filterText.value ?? '')
  if (!keyword) return [{ text: source, highlight: false }]

  const lowerSource = source.toLowerCase()
  const lowerKeyword = keyword.toLowerCase()
  if (!lowerKeyword) return [{ text: source, highlight: false }]

  const parts = []
  let cursor = 0
  while (true) {
    const idx = lowerSource.indexOf(lowerKeyword, cursor)
    if (idx === -1) break
    if (idx > cursor) parts.push({ text: source.slice(cursor, idx), highlight: false })
    parts.push({ text: source.slice(idx, idx + keyword.length), highlight: true })
    cursor = idx + keyword.length
    if (keyword.length === 0) break
  }
  if (cursor < source.length) parts.push({ text: source.slice(cursor), highlight: false })
  return parts.length ? parts : [{ text: source, highlight: false }]
}

// Icon Helpers
const getTypeIcon = (type) => {
    const map = { school: School, college: Reading, department: OfficeBuilding, office: User }
    return map[type] || OfficeBuilding
}

const getTypeColor = (type) => {
    const map = { school: '#409EFF', college: '#E6A23C', department: '#67C23A', office: '#909399' }
    return map[type] || '#909399'
}

const getTypeName = (type) => {
    const map = { school: '学校', college: '学院/单位', department: '系/部门', office: '科室/实验室' }
    return map[type] || type
}

const getTypeTagEffect = (type) => {
    return type === 'school' ? 'dark' : 'plain'
}

// Actions
const handleRefresh = () => {
    loading.value = true
    setTimeout(() => {
        loading.value = false
        ElMessage.success('数据已刷新')
    }, 500)
}

const toggleExpandAll = () => {
    isExpandAll.value = !isExpandAll.value
    // Re-render key hack or iterating store is needed for dynamic expand-all change
    // For simplicity, we can traverse data
    const expandRecursive = (nodes, expand) => {
        nodes.forEach(node => {
            node.expanded = expand
            const treeNode = treeRef.value.getNode(node)
            if(treeNode) treeNode.expanded = expand
            if (node.children) expandRecursive(node.children, expand)
        })
    }
    // Element Plus tree exposes store
    const store = treeRef.value.store
    const getAllNodes = (root) => {
        let nodes = []
        const traverse = (n) => {
            nodes.push(n)
            if(n.childNodes) n.childNodes.forEach(traverse)
        }
        traverse(root)
        return nodes
    }
    getAllNodes(store.root).forEach(node => node.expanded = isExpandAll.value)
}

const handleExport = () => {
    const dataStr = JSON.stringify(orgData.value, null, 2)
    const blob = new Blob([dataStr], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `organization_export_${new Date().toISOString().split('T')[0]}.json`
    link.click()
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
}

// CRUD
const handleAddRoot = () => {
    isRoot.value = true
    currentParent.value = null
    currentEditNode.value = null
    formType.value = 'create'
    dialogTitle.value = '新建根节点'
    resetForm()
    form.type = 'school'
    dialogVisible.value = true
}

const append = (data) => {
  isRoot.value = false
  currentParent.value = data
  currentEditNode.value = null
  formType.value = 'create'
  dialogTitle.value = `在 [${data.label}] 下添加`
  resetForm()
  // Smart default type
  if(data.type === 'school') form.type = 'college'
  else if(data.type === 'college') form.type = 'department'
  else form.type = 'office'
  
  dialogVisible.value = true
}

const handleEdit = (data) => {
    isRoot.value = data.type === 'school'
    currentParent.value = null // Not needed for edit
    currentEditNode.value = data
    formType.value = 'edit'
    dialogTitle.value = `编辑 [${data.label}]`
    
    // Fill form
    form.id = data.id
    form.label = data.label
    form.type = data.type
    form.code = data.code || ''
    form.manager = data.manager || ''
    form.description = data.description || ''
    form.status = data.status !== false // default true
    
    dialogVisible.value = true
}

const remove = (node, data) => {
  ElMessageBox.confirm(
    `确定要删除 [${data.label}] 及其所有下级节点吗？此操作不可恢复。`,
    '警告',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    }
  ).then(() => {
      const parent = node.parent
      const children = parent.data.children || parent.data
      const index = children.findIndex((d) => d.id === data.id)
      children.splice(index, 1)
      ElMessage.success('删除成功')
  }).catch(() => {})
}

const handleSave = async () => {
    if (!formRef.value) return
    await formRef.value.validate((valid) => {
        if (valid) {
            saving.value = true
            // Simulate API call
            setTimeout(() => {
                if (formType.value === 'create') {
                    const newChild = { 
                        id: Date.now(), 
                        label: form.label, 
                        type: form.type,
                        code: form.code,
                        manager: form.manager,
                        description: form.description,
                        status: form.status,
                        children: [] 
                    }
                    if (!currentParent.value) {
                        orgData.value.push(newChild)
                    } else {
                        if (!currentParent.value.children) {
                            currentParent.value.children = []
                        }
                        currentParent.value.children.push(newChild)
                        // Auto expand parent
                         nextTick(() => {
                            const node = treeRef.value.getNode(currentParent.value)
                            if(node) node.expanded = true
                        })
                    }
                    ElMessage.success('创建成功')
                } else {
                    // Update
                    if (currentEditNode.value) {
                        currentEditNode.value.label = form.label
                        currentEditNode.value.type = form.type
                        currentEditNode.value.code = form.code
                        currentEditNode.value.manager = form.manager
                        currentEditNode.value.description = form.description
                        currentEditNode.value.status = form.status
                    }
                    ElMessage.success('更新成功')
                }
                saving.value = false
                dialogVisible.value = false
            }, 500)
        }
    })
}

const resetForm = () => {
    form.id = null
    form.label = ''
    form.code = ''
    form.manager = ''
    form.description = ''
    form.status = true
    if(formRef.value) formRef.value.resetFields()
}

// Drag & Drop
const allowDrag = (draggingNode) => {
    // Optional: Prevent dragging root
    return true
}

const allowDrop = (draggingNode, dropNode, type) => {
    // Optional: Rules for dropping
    return true
}

const handleDrop = (draggingNode, dropNode, dropType, ev) => {
    ElMessage.success(`已将 [${draggingNode.data.label}] 移动到 [${dropNode.data.label}] ${dropType === 'inner' ? '内部' : (dropType === 'before' ? '之前' : '之后')}`)
}

</script>

<style scoped>
.org-management {
    padding: 20px;
    height: 100%;
    display: flex;
    flex-direction: column;
}

.box-card {
    display: flex;
    flex-direction: column;
    height: 100%;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.title {
    font-size: 16px;
    font-weight: bold;
}

.filter-container {
    margin-bottom: 20px;
}

.tree-container {
    flex: 1;
    overflow-y: auto;
    min-height: 400px;
}

.custom-tree-node {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  padding-right: 8px;
  overflow: hidden; /* Prevent overflow */
}

.custom-tree-node.is-disabled {
    opacity: 0.6;
}

.custom-tree-node.is-disabled .node-label {
    text-decoration: line-through;
    color: #909399;
}

.node-content {
    display: flex;
    align-items: center;
    overflow: hidden;
    flex: 1;
}

.node-main {
    display: flex;
    align-items: center;
    white-space: nowrap;
}

.node-label {
    margin-left: 5px;
    font-weight: 500;
}

.node-highlight {
    color: var(--el-color-primary);
    font-weight: bold;
}

.node-info {
    margin-left: 20px;
    display: flex;
    align-items: center;
    color: #909399;
    font-size: 12px;
}

.info-item {
    margin-right: 15px;
    display: flex;
    align-items: center;
    gap: 4px;
}

.node-actions {
    display: flex;
    opacity: 0;
    transition: opacity 0.2s;
}

.custom-tree-node:hover .node-actions {
    opacity: 1;
}

.ml-2 { margin-left: 8px; }

/* Responsive */
@media (max-width: 768px) {
    .node-info {
        display: none;
    }
    .node-actions {
        opacity: 1; /* Always show on mobile */
    }
    .tag-type {
        display: none;
    }
}
</style>
