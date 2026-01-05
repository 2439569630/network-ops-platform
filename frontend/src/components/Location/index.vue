<template>
  <div class="location-management">
    <el-card class="box-card" shadow="never">
      <template #header>
        <div class="card-header">
          <div class="left-actions">
            <span class="title">位置体系管理</span>
          </div>
          <div class="right-actions">
             <el-button-group>
                <el-button :icon="Plus" type="primary" @click="handleAddRoot">新建校区</el-button>
                <el-button :icon="Download" @click="handleExport">导出数据</el-button>
                <el-button :icon="Refresh" @click="handleRefresh">刷新</el-button>
                <el-button :icon="Sort" @click="toggleExpandAll">{{ isExpandAll ? '折叠全部' : '展开全部' }}</el-button>
            </el-button-group>
          </div>
        </div>
      </template>

      <div class="layout-container">
          <!-- Left Tree (30%) -->
          <div class="tree-panel">
               <div class="filter-box">
                    <el-input 
                        v-model="filterText" 
                        placeholder="搜索位置/编码" 
                        :prefix-icon="Search"
                        clearable
                    />
               </div>
               
               <div class="tree-wrapper" v-loading="loading">
                   <el-tree
                    ref="treeRef"
                    :data="locationData"
                    :props="defaultProps"
                    :filter-node-method="filterNode"
                    node-key="id"
                    :default-expand-all="isExpandAll"
                    draggable
                    :allow-drop="allowDrop"
                    :allow-drag="allowDrag"
                    @node-drop="handleDrop"
                    @node-click="handleNodeClick"
                    highlight-current
                    :expand-on-click-node="false"
                  >
                    <template #default="{ node, data }">
                        <div class="custom-tree-node" :class="{ 'is-disabled': data.status === false }">
                             <span class="node-main">
                                 <!-- Type Icon -->
                                 <el-icon :color="getTypeColor(data.type)" class="node-icon">
                                     <component :is="getTypeIcon(data.type)" />
                                 </el-icon>
                                 
                                 <!-- Label -->
                                 <span class="node-label" v-html="highlightText(node.label)"></span>
                                 
                                 <!-- Count Badge -->
                                 <span v-if="data.children && data.children.length > 0" class="count-badge">
                                     ({{data.children.length}})
                                 </span>

                                  <!-- Status Dot -->
                                 <span v-if="data.status === false" class="status-dot disabled" title="停用"></span>
                             </span>
                        </div>
                    </template>
                  </el-tree>
               </div>
          </div>

          <!-- Right Detail/Edit Panel (70%) -->
          <div class="detail-panel" v-loading="detailLoading">
              <div v-if="currentNode" class="detail-content">
                  <!-- Header -->
                  <div class="detail-header">
                      <div class="header-title">
                          <el-icon :size="24" :color="getTypeColor(currentNode.type)" style="margin-right: 10px">
                               <component :is="getTypeIcon(currentNode.type)" />
                          </el-icon>
                          <h2>{{ currentNode.label }}</h2>
                          <el-tag :type="getTypeTagEffect(currentNode.type)" effect="dark" class="ml-2">
                              {{ getTypeName(currentNode.type) }}
                          </el-tag>
                          <el-tag v-if="currentNode.status === false" type="danger" effect="dark" class="ml-2">已停用</el-tag>
                          <el-tag v-else type="success" effect="plain" class="ml-2">使用中</el-tag>
                      </div>
                      <div class="header-actions">
                           <el-button type="primary" :icon="Edit" @click="handleEdit(currentNode)">编辑</el-button>
                           <el-button type="success" :icon="Printer" @click="handleQrCode(currentNode)">二维码</el-button>
                      </div>
                  </div>

                  <!-- Breadcrumb -->
                  <div class="breadcrumb-nav">
                       <el-breadcrumb separator="/">
                            <el-breadcrumb-item v-for="(item, index) in breadcrumbList" :key="index">{{ item }}</el-breadcrumb-item>
                       </el-breadcrumb>
                  </div>

                  <!-- Info Cards -->
                  <el-row :gutter="20" class="mt-20">
                      <el-col :span="16">
                           <el-descriptions title="基本信息" :column="2" border>
                                <el-descriptions-item label="位置编码">
                                    <el-tag type="info">{{ currentNode.code || '未设置' }}</el-tag>
                                </el-descriptions-item>
                                <el-descriptions-item label="管理单位">{{ currentNode.managerDept || '未设置' }}</el-descriptions-item>
                                <el-descriptions-item label="容量/面积">{{ currentNode.capacity ? currentNode.capacity + '人' : '-' }} / {{ currentNode.area ? currentNode.area + '㎡' : '-' }}</el-descriptions-item>
                                <el-descriptions-item label="负责人">{{ currentNode.manager || '未设置' }} ({{ currentNode.phone || '-' }})</el-descriptions-item>
                                <el-descriptions-item label="详细地址" :span="2">{{ currentNode.address || '-' }}</el-descriptions-item>
                                <el-descriptions-item label="备注" :span="2">{{ currentNode.description || '无' }}</el-descriptions-item>
                           </el-descriptions>

                           <div class="section-title mt-20">
                                <span>关联设备 ({{ deviceList.length }})</span>
                                <el-button link type="primary" size="small">查看全部</el-button>
                           </div>
                           <el-table :data="deviceList" style="width: 100%" size="small" border stripe>
                                <el-table-column prop="name" label="设备名称" />
                                <el-table-column prop="type" label="类型" width="100" />
                                <el-table-column prop="status" label="状态" width="80">
                                     <template #default="{ row }">
                                         <el-tag :type="row.status === 'online' ? 'success' : 'danger'" size="small">
                                             {{ row.status === 'online' ? '在线' : '离线' }}
                                         </el-tag>
                                     </template>
                                </el-table-column>
                           </el-table>
                      </el-col>

                      <el-col :span="8">
                           <!-- Quick Actions -->
                           <el-card shadow="hover" class="action-card">
                               <template #header>快捷操作</template>
                               <div class="quick-actions">
                                   <el-button class="qa-btn" :icon="Plus" @click="append(currentNode)">添加子位置</el-button>
                                   <el-button class="qa-btn" :icon="CopyDocument" @click="handleCopy(currentNode)">复制结构</el-button>
                                   <el-button class="qa-btn" type="danger" plain :icon="Delete" @click="remove(currentNode)">删除位置</el-button>
                               </div>
                           </el-card>

                           <!-- Stats -->
                           <el-card shadow="hover" class="mt-20 stats-card">
                               <div class="stat-item">
                                   <div class="label">创建时间</div>
                                   <div class="value">{{ formatDate(currentNode.createdAt) }}</div>
                               </div>
                               <div class="stat-item">
                                   <div class="label">最后更新</div>
                                   <div class="value">{{ formatDate(currentNode.updatedAt) }}</div>
                               </div>
                           </el-card>
                      </el-col>
                  </el-row>

              </div>
              <div class="empty-state" v-else>
                  <el-empty description="请选择左侧位置节点查看详情" :image-size="200" />
              </div>
          </div>
      </div>
    </el-card>

    <!-- Create/Edit Dialog -->
    <el-dialog 
        v-model="dialogVisible" 
        :title="dialogTitle" 
        width="600px"
        :close-on-click-modal="false"
        destroy-on-close
    >
      <el-form ref="formRef" :model="form" :rules="rules" label-width="100px">
        <el-row :gutter="20">
            <el-col :span="24">
                <el-form-item label="名称" prop="label">
                  <el-input v-model="form.label" placeholder="如：教学楼A" maxlength="50" show-word-limit />
                </el-form-item>
            </el-col>
            <el-col :span="12">
                <el-form-item label="类型" prop="type">
                  <el-select v-model="form.type" placeholder="请选择类型" :disabled="formType === 'edit' && form.type === 'campus'">
                    <el-option label="校区" value="campus" v-if="isRoot || form.type === 'campus'" />
                    <el-option label="楼宇" value="building" />
                    <el-option label="楼层" value="floor" />
                    <el-option label="房间/区域" value="room" />
                  </el-select>
                </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="编码" prop="code">
                    <el-input v-model="form.code" placeholder="唯一编码" />
                 </el-form-item>
            </el-col>
            <el-col :span="24">
                <el-form-item label="管理单位" prop="managerDept">
                     <el-select v-model="form.managerDept" placeholder="选择管理单位" filterable style="width: 100%">
                         <el-option label="教务处" value="教务处" />
                         <el-option label="信息化办公室" value="信息化办公室" />
                         <el-option label="后勤处" value="后勤处" />
                         <el-option label="计算机学院" value="计算机学院" />
                     </el-select>
                </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="负责人">
                    <el-input v-model="form.manager" placeholder="姓名" />
                 </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="联系电话">
                    <el-input v-model="form.phone" placeholder="电话" />
                 </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="容量(人)">
                    <el-input-number v-model="form.capacity" :min="0" style="width: 100%" />
                 </el-form-item>
            </el-col>
            <el-col :span="12">
                 <el-form-item label="面积(㎡)">
                    <el-input-number v-model="form.area" :min="0" :precision="2" style="width: 100%" />
                 </el-form-item>
            </el-col>
            <el-col :span="24">
                 <el-form-item label="详细地址">
                    <el-input v-model="form.address" placeholder="详细地理位置描述" />
                 </el-form-item>
            </el-col>
            <el-col :span="24">
                 <el-form-item label="备注">
                    <el-input v-model="form.description" type="textarea" :rows="2" />
                 </el-form-item>
            </el-col>
            <el-col :span="24">
                 <el-form-item label="状态">
                    <el-switch v-model="form.status" active-text="启用" inactive-text="停用" />
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

    <!-- QR Code Dialog -->
    <el-dialog v-model="qrVisible" title="位置二维码" width="300px" center>
        <div class="qr-container" v-if="qrNode">
            <div class="qr-title">{{ qrNode.label }}</div>
            <div class="qr-code-mock">
                <!-- Placeholder for QR Code -->
                <el-icon :size="150" color="#333"><img src="https://api.qrserver.com/v1/create-qr-code/?size=150x150&data=LocationID:123" alt="QR" /></el-icon>
            </div>
            <div class="qr-info">ID: {{ qrNode.code || qrNode.id }}</div>
            <div class="qr-hint">扫码报修 / 查看详情</div>
        </div>
        <template #footer>
            <el-button type="primary" @click="downloadQr">下载二维码</el-button>
        </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, reactive, nextTick, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
    Plus, Edit, Delete, Search, Download, Refresh, Sort, 
    School, OfficeBuilding, House, Location,
    Printer, CopyDocument, Warning
} from '@element-plus/icons-vue'

// --- State ---
const filterText = ref('')
const treeRef = ref(null)
const currentNode = ref(null)
const loading = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const isExpandAll = ref(true)

// Dialogs
const dialogVisible = ref(false)
const dialogTitle = ref('新建位置')
const formType = ref('create')
const formRef = ref(null)
const isRoot = ref(false)
const currentParent = ref(null)

const qrVisible = ref(false)
const qrNode = ref(null)

// Form Data
const form = reactive({
    id: null,
    label: '',
    type: 'building',
    code: '',
    managerDept: '',
    manager: '',
    phone: '',
    address: '',
    capacity: 0,
    area: 0,
    description: '',
    status: true
})

const rules = {
    label: [{ required: true, message: '请输入名称', trigger: 'blur' }],
    type: [{ required: true, message: '请选择类型', trigger: 'change' }],
    code: [{ required: true, message: '请输入编码', trigger: 'blur' }],
    managerDept: [{ required: true, message: '请选择管理单位', trigger: 'change' }]
}

// Data
const defaultProps = {
  children: 'children',
  label: 'label',
}

const locationData = ref([
    {
        id: 1,
        label: '主校区',
        type: 'campus',
        code: 'CAMP01',
        managerDept: '校办',
        status: true,
        createdAt: '2023-01-01',
        updatedAt: '2023-12-01',
        children: [
            {
                id: 2,
                label: '教学楼A',
                type: 'building',
                code: 'BLD-A',
                managerDept: '教务处',
                status: true,
                createdAt: '2023-01-02',
                updatedAt: '2023-12-05',
                children: [
                    {
                        id: 3,
                        label: '1楼',
                        type: 'floor',
                        code: 'BLD-A-1F',
                        managerDept: '教务处',
                        status: true,
                        children: [
                            { id: 4, label: '101教室', type: 'room', code: '101', managerDept: '教务处', status: true, capacity: 50 },
                            { id: 5, label: '102教室', type: 'room', code: '102', managerDept: '教务处', status: true, capacity: 50 }
                        ]
                    }
                ]
            }
        ]
    }
])

const deviceList = ref([])

// --- Watchers ---
watch(filterText, (val) => {
  treeRef.value?.filter(val)
})

// --- Computed ---
const breadcrumbList = computed(() => {
    if (!currentNode.value) return []
    // Need to traverse up to find path. 
    // Since element tree data structure is nested, we might need a helper or use tree node properties
    // Using a simple hack: Node object from tree has parent reference
    const list = []
    let node = treeRef.value.getNode(currentNode.value.id)
    while(node && node.level > 0) {
        list.unshift(node.label)
        node = node.parent
    }
    return list
})

// --- Methods ---

const filterNode = (value, data) => {
  if (!value) return true
  const lowerValue = value.toLowerCase()
  return data.label.toLowerCase().includes(lowerValue) || 
         (data.code && data.code.toLowerCase().includes(lowerValue))
}

const highlightText = (text) => {
    if (!filterText.value) return text;
    const reg = new RegExp(filterText.value, 'gi');
    return text.replace(reg, (match) => `<span style="color: var(--el-color-primary); font-weight: bold">${match}</span>`);
}

const handleNodeClick = (data) => {
    detailLoading.value = true
    currentNode.value = data
    // Simulate fetching details & devices
    setTimeout(() => {
        // Mock devices
        deviceList.value = [
            { name: 'Switch-01', type: '交换机', status: 'online' },
            { name: 'AP-01', type: '无线AP', status: 'online' },
            { name: 'PC-Teacher', type: 'PC', status: 'offline' }
        ]
        detailLoading.value = false
    }, 300)
}

// Icons & Styles
const getTypeIcon = (type) => {
    const map = { campus: School, building: OfficeBuilding, floor: House, room: Location }
    return map[type] || Location
}

const getTypeColor = (type) => {
    const map = { campus: '#409EFF', building: '#E6A23C', floor: '#67C23A', room: '#909399' }
    return map[type] || '#909399'
}

const getTypeName = (type) => {
    const map = { campus: '校区', building: '楼宇', floor: '楼层', room: '房间/区域' }
    return map[type] || type
}

const getTypeTagEffect = (type) => {
    return type === 'campus' ? 'dark' : 'plain'
}

const formatDate = (dateStr) => {
    if(!dateStr) return '-'
    return new Date(dateStr).toLocaleDateString()
}

// Toolbar Actions
const handleRefresh = () => {
    loading.value = true
    setTimeout(() => {
        loading.value = false
        ElMessage.success('数据已刷新')
    }, 500)
}

const toggleExpandAll = () => {
    isExpandAll.value = !isExpandAll.value
    // Element Plus tree stores
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
    ElMessage.success('正在导出Excel...')
}

// CRUD
const handleAddRoot = () => {
    isRoot.value = true
    currentParent.value = null
    formType.value = 'create'
    dialogTitle.value = '新建校区'
    resetForm()
    form.type = 'campus'
    dialogVisible.value = true
}

const append = (data) => {
    isRoot.value = false
    currentParent.value = data
    formType.value = 'create'
    dialogTitle.value = `在 [${data.label}] 下添加`
    resetForm()
    // Auto select next level type
    if(data.type === 'campus') form.type = 'building'
    else if(data.type === 'building') form.type = 'floor'
    else if(data.type === 'floor') form.type = 'room'
    else form.type = 'room'
    
    form.managerDept = data.managerDept 
    dialogVisible.value = true
}

const handleEdit = (data) => {
    isRoot.value = data.type === 'campus'
    currentParent.value = null
    formType.value = 'edit'
    dialogTitle.value = `编辑 [${data.label}]`
    
    // Fill form
    Object.assign(form, data)
    form.status = data.status !== false
    
    dialogVisible.value = true
}

const handleCopy = (data) => {
    ElMessageBox.confirm(`确定要复制 [${data.label}] 及其下级结构吗？`, '提示', {
        confirmButtonText: '确定',
        cancelButtonText: '取消'
    }).then(() => {
        ElMessage.success('复制成功')
    })
}

const remove = (data) => {
    ElMessageBox.confirm(
        `确定要删除 [${data.label}] 吗？\n注意：如果该位置下有设备，请先迁移设备。`,
        '删除确认',
        {
            confirmButtonText: '确定删除',
            cancelButtonText: '取消',
            type: 'warning',
            icon: Warning
        }
    ).then(() => {
        // Recursive remove
        const removeNode = (list, id) => {
            for(let i=0; i<list.length; i++) {
                if(list[i].id === id) {
                    list.splice(i, 1)
                    return true
                }
                if(list[i].children) {
                    if(removeNode(list[i].children, id)) return true
                }
            }
            return false
        }
        removeNode(locationData.value, data.id)
        currentNode.value = null
        ElMessage.success('删除成功')
    }).catch(() => {})
}

const handleSave = async () => {
    if (!formRef.value) return
    await formRef.value.validate((valid) => {
        if (valid) {
            saving.value = true
            setTimeout(() => {
                const now = new Date().toISOString()
                if (formType.value === 'create') {
                    const newChild = { 
                        ...form,
                        id: Date.now(), 
                        children: [],
                        createdAt: now,
                        updatedAt: now
                    }
                    if (!currentParent.value) {
                        locationData.value.push(newChild)
                    } else {
                        if (!currentParent.value.children) {
                            currentParent.value.children = []
                        }
                        currentParent.value.children.push(newChild)
                        nextTick(() => {
                            const node = treeRef.value.getNode(currentParent.value)
                            if(node) node.expanded = true
                        })
                    }
                    ElMessage.success('创建成功')
                } else {
                    // Update - need to find reference in real data, but here form is copied
                    // In real app, we update backend. Here we update currentNode if it matches
                    if(currentNode.value && currentNode.value.id === form.id) {
                         Object.assign(currentNode.value, form)
                         currentNode.value.updatedAt = now
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
    form.managerDept = ''
    form.manager = ''
    form.phone = ''
    form.address = ''
    form.capacity = 0
    form.area = 0
    form.description = ''
    form.status = true
    if(formRef.value) formRef.value.resetFields()
}

// Drag & Drop
const allowDrag = (draggingNode) => true
const allowDrop = (draggingNode, dropNode, type) => true
const handleDrop = (draggingNode, dropNode, dropType, ev) => {
    ElMessage.success(`已移动位置`)
}

// QR Code
const handleQrCode = (data) => {
    qrNode.value = data
    qrVisible.value = true
}

const downloadQr = () => {
    ElMessage.success('二维码已开始下载')
    qrVisible.value = false
}

</script>

<style scoped>
.location-management {
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

.layout-container {
    display: flex;
    gap: 20px;
    height: calc(100vh - 200px); /* Responsive height */
    min-height: 500px;
}

/* Tree Panel */
.tree-panel {
    flex: 3; /* 30% */
    border-right: 1px solid #eee;
    padding-right: 20px;
    display: flex;
    flex-direction: column;
}
.filter-box {
    margin-bottom: 10px;
}
.tree-wrapper {
    flex: 1;
    overflow-y: auto;
}
.custom-tree-node {
    flex: 1;
    overflow: hidden;
}
.node-main {
    display: flex;
    align-items: center;
    font-size: 14px;
}
.node-icon {
    margin-right: 6px;
}
.node-label {
    margin-right: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.count-badge {
    color: #909399;
    font-size: 12px;
}
.status-dot {
    width: 6px;
    height: 6px;
    border-radius: 50%;
    margin-left: 5px;
}
.status-dot.disabled {
    background-color: #f56c6c;
}
.custom-tree-node.is-disabled .node-label {
    color: #909399;
    text-decoration: line-through;
}

/* Detail Panel */
.detail-panel {
    flex: 7; /* 70% */
    padding-left: 20px;
    overflow-y: auto;
}

.detail-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
    padding-bottom: 20px;
    border-bottom: 1px solid #eee;
}
.header-title {
    display: flex;
    align-items: center;
}
.header-title h2 {
    margin: 0;
    font-size: 20px;
    font-weight: bold;
}
.ml-2 { margin-left: 10px; }
.mt-20 { margin-top: 20px; }

.section-title {
    font-size: 14px;
    font-weight: bold;
    color: #303133;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.action-card, .stats-card {
    background-color: #fcfcfc;
}
.quick-actions {
    display: flex;
    flex-direction: column;
    gap: 10px;
}
.qa-btn {
    margin-left: 0 !important;
    justify-content: flex-start;
}

.stat-item {
    display: flex;
    justify-content: space-between;
    margin-bottom: 10px;
    font-size: 13px;
}
.stat-item .label { color: #909399; }

/* QR Code */
.qr-container {
    text-align: center;
}
.qr-title {
    font-weight: bold;
    margin-bottom: 10px;
}
.qr-code-mock {
    margin: 10px 0;
}
.qr-info {
    font-size: 12px;
    color: #666;
}
.qr-hint {
    font-size: 12px;
    color: #999;
    margin-top: 5px;
}

.empty-state {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
}
</style>
