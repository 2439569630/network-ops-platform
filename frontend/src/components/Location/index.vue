<template>
  <div class="location-container" :class="{ 'is-mobile': isMobile }" v-loading="globalLoading">
    <!-- 侧边栏：位置树 -->
    <div class="sidebar-card" v-show="!isMobile || !showMobileDetail">
      <div class="sidebar-header">
        <span class="sidebar-title">位置导航</span>
        <el-button-group class="sidebar-actions">
           <el-tooltip content="刷新" placement="top">
                <el-button :icon="Refresh" circle size="small" @click="handleRefresh" />
           </el-tooltip>
           <el-tooltip content="展开/折叠" placement="top">
                <el-button :icon="Sort" circle size="small" @click="toggleExpandAll" />
           </el-tooltip>
        </el-button-group>
      </div>
      
      <div class="sidebar-action-area">
         <el-button type="primary" class="full-width-btn" :icon="Plus" :disabled="!canAdd" @click="handleAddRoot" plain>新建节点</el-button>
      </div>

      <div class="filter-wrapper">
        <el-input 
            v-model="filterText" 
            placeholder="输入关键字过滤..." 
            :prefix-icon="Search"
            clearable
        />
      </div>
      
      <div class="tree-content">
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
                         <component 
                            :is="getTypeIcon(data.type)" 
                            class="node-icon" 
                            :style="{ color: getTypeColor(data.type), width: '1.2em', height: '1.2em', marginRight: '8px', verticalAlign: '-2px' }"
                         />
                         <span class="node-label">
                            <template v-for="(p, idx) in highlightParts(node.label)" :key="idx">
                                <span v-if="p.highlight" class="node-highlight">{{ p.text }}</span>
                                <span v-else>{{ p.text }}</span>
                            </template>
                         </span>
                         <span v-if="data.status === false" class="status-badge off">停</span>
                     </span>
                </div>
            </template>
          </el-tree>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="main-content" v-show="!isMobile || showMobileDetail">
      <div v-if="currentNode" class="content-wrapper">
        <!-- 顶部头信息 -->
        <div class="content-header">
            <div class="header-left">
                <div class="mobile-back-row" v-if="isMobile">
                    <el-button link :icon="ArrowLeft" @click="handleMobileBack" class="back-btn">返回列表</el-button>
                </div>
                <div class="breadcrumb-area" v-else>
                    <el-breadcrumb separator="/">
                        <el-breadcrumb-item v-for="(item, index) in breadcrumbList" :key="index">{{ item }}</el-breadcrumb-item>
                    </el-breadcrumb>
                </div>
                <div class="title-row">
                    <h1 class="node-title">{{ currentNode.label }}</h1>
                    <el-tag :type="getTypeTagType(currentNode.type)" effect="dark" class="ml-3">
                        {{ getTypeName(currentNode.type) }}
                    </el-tag>
                    <el-tag v-if="currentNode.status === false" type="danger" effect="dark" class="ml-2">已停用</el-tag>
                    <el-tag v-else type="success" effect="plain" class="ml-2">正常</el-tag>
                </div>
            </div>
            <div class="header-right">
                <el-button type="primary" :icon="Edit" :disabled="!canEdit" @click="handleEdit(currentNode)">编辑</el-button>
                <el-dropdown trigger="click" class="ml-2" @command="handleCommand">
                    <el-button>
                        更多操作<el-icon class="el-icon--right"><arrow-down /></el-icon>
                    </el-button>
                    <template #dropdown>
                        <el-dropdown-menu>
                            <el-dropdown-item :icon="Plus" :disabled="!canAdd" command="add">添加子位置</el-dropdown-item>
                            <el-dropdown-item :icon="CopyDocument" command="copy">复制结构</el-dropdown-item>
                            <el-dropdown-item divided :icon="Delete" :disabled="!canDel" command="delete" style="color: #f56c6c">删除位置</el-dropdown-item>
                        </el-dropdown-menu>
                    </template>
                </el-dropdown>
            </div>
        </div>

        <!-- 统计卡片行 -->
        <div class="stats-row">
            <div class="stat-card">
                <div class="stat-icon bg-blue">
                    <el-icon><Key /></el-icon>
                </div>
                <div class="stat-info">
                    <div class="stat-label">绑定角色</div>
                    <div class="stat-value">{{ (currentNode.roleIds || []).length }}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-green">
                    <el-icon><User /></el-icon>
                </div>
                <div class="stat-info">
                    <div class="stat-label">管理员</div>
                    <div class="stat-value">{{ (currentNode.userIds || []).length }}</div>
                </div>
            </div>
            <div class="stat-card">
                <div class="stat-icon bg-purple">
                    <el-icon><Monitor /></el-icon>
                </div>
                <div class="stat-info">
                    <div class="stat-label">关联设备</div>
                    <div class="stat-value">{{ deviceList.length }}</div>
                </div>
            </div>
             <div class="stat-card">
                <div class="stat-icon bg-orange">
                    <el-icon><OfficeBuilding /></el-icon>
                </div>
                <div class="stat-info">
                    <div class="stat-label">下级位置</div>
                    <div class="stat-value">{{ currentNode.children ? currentNode.children.length : 0 }}</div>
                </div>
            </div>
        </div>

        <!-- 详细信息与设备 -->
        <div class="details-grid">
            <!-- 左侧：基本信息 -->
            <div class="info-section">
                <div class="section-header">
                    <span class="section-title">基本信息</span>
                </div>
                <el-descriptions :column="1" border size="large">
                    <el-descriptions-item label="位置编码">
                        <el-tag type="info" effect="plain">{{ currentNode.code || '未设置' }}</el-tag>
                    </el-descriptions-item>
                    <el-descriptions-item label="管理员">
                        <div v-if="currentNodeUserLabels.length" class="tag-list">
                            <el-tag v-for="t in currentNodeUserLabels" :key="t" type="success" effect="plain" class="mr-1">{{ t }}</el-tag>
                        </div>
                        <span v-else>-</span>
                    </el-descriptions-item>
                    <el-descriptions-item label="详细地址">{{ currentNode.address || '-' }}</el-descriptions-item>
                    <el-descriptions-item label="备注">
                         <span class="desc-text">{{ currentNode.description || '暂无备注' }}</span>
                    </el-descriptions-item>
                    <el-descriptions-item label="创建时间">{{ formatDate(currentNode.createdAt) }}</el-descriptions-item>
                    <el-descriptions-item label="最后更新">{{ formatDate(currentNode.updatedAt) }}</el-descriptions-item>
                </el-descriptions>
            </div>

            <!-- 右侧：关联设备 -->
            <div class="device-section">
                <div class="section-header">
                    <span class="section-title">关联设备列表</span>
                    <div class="header-actions">
                        <template v-if="!canBindDevice">
                            <el-tooltip content="该节点类型无法直接绑定设备，请在下级位置添加" placement="top">
                                <span>
                                    <el-button type="primary" link :icon="Plus" disabled>添加设备</el-button>
                                </span>
                            </el-tooltip>
                        </template>
                        <el-button v-else type="primary" link :icon="Plus" @click="handleAddDevice">添加设备</el-button>
                        <el-button link type="primary">查看全部</el-button>
                    </div>
                </div>
                <el-table :data="deviceList" style="width: 100%" height="400" stripe>
                    <el-table-column prop="device_name" label="设备名称" show-overflow-tooltip />
                    <el-table-column prop="type" label="类型" width="100" />
                    <el-table-column prop="ipv4" label="IP地址" width="130" />
                    <el-table-column prop="status" label="状态" width="90">
                            <template #default="{ row }">
                                <el-tag :type="getDeviceStatusTagType(getDeviceStatusModel(row))" size="small" effect="dark">
                                    {{ getDeviceStatusText(getDeviceStatusModel(row), nowTick) }}
                                </el-tag>
                            </template>
                    </el-table-column>
                    <el-table-column label="操作" width="150" align="center" fixed="right">
                        <template #default="{ row }">
                             <el-button 
                                type="danger" 
                                link 
                                :icon="Delete" 
                                @click="handleRemoveDevice(row)"
                                :disabled="!canEdit"
                             />
                        </template>
                    </el-table-column>
                </el-table>
            </div>
        </div>

      </div>
      <div class="empty-placeholder" v-else>
          <img src="https://gw.alipayobjects.com/zos/antfincdn/ZHrcdLPrvN/empty.svg" alt="Empty" width="200" />
          <p>请选择左侧位置节点查看详情</p>
      </div>
    </div>

    <!-- Create/Edit Dialog -->
    <el-dialog 
        v-model="dialogVisible" 
        :title="dialogTitle" 
        :width="isMobile ? '90%' : '580px'"
        :close-on-click-modal="false"
        destroy-on-close
        class="location-dialog"
        center
        append-to-body
    >
      <el-form ref="formRef" :model="form" :rules="rules" :label-width="isMobile ? '70px' : '90px'" class="location-form" hide-required-asterisk>
        <!-- 核心信息 -->
        <div class="form-section">
            <el-row :gutter="20">
                <el-col :span="24">
                    <el-form-item label="名称" prop="label">
                      <el-input v-model="form.label" placeholder="如：教学楼A" maxlength="50" show-word-limit>
                          <template #prefix><el-icon><OfficeBuilding /></el-icon></template>
                      </el-input>
                    </el-form-item>
                </el-col>
                <el-col :span="isMobile ? 24 : 12">
                    <el-form-item label="类型" prop="type">
                      <el-select v-model="form.type" placeholder="请选择类型" :disabled="formType === 'edit' && form.type === 'school'" style="width: 100%">
                        <template #prefix><el-icon><Menu /></el-icon></template>
                        <el-option label="学校" value="school" v-if="isRoot || form.type === 'school'" />
                        <el-option label="校区" value="campus" />
                        <el-option label="院系" value="department" />
                        <el-option label="教学楼" value="building" />
                        <el-option label="楼层" value="floor" />
                        <el-option label="教室" value="classroom" />
                        <el-option label="房间/区域" value="room" />
                      </el-select>
                    </el-form-item>
                </el-col>
                 <el-col :span="isMobile ? 24 : 12">
                     <el-form-item label="状态">
                        <el-radio-group v-model="form.status" style="width: 100%">
                            <el-radio-button :label="true">启用</el-radio-button>
                            <el-radio-button :label="false">停用</el-radio-button>
                        </el-radio-group>
                     </el-form-item>
                </el-col>
                 <el-col :span="24">
                     <el-form-item label="编码">
                        <el-input v-model="form.code" placeholder="系统自动生成（创建后显示）" disabled class="code-input">
                            <template #prefix><el-icon><Lock /></el-icon></template>
                        </el-input>
                     </el-form-item>
                </el-col>
            </el-row>
        </div>

        <!-- 详细信息 -->
        <div class="form-section mt-3">
            <el-row :gutter="20">
                <el-col :span="24">
                     <el-form-item label="详细地址">
                        <el-input v-model="form.address" placeholder="详细地理位置描述" :rows="2" type="textarea" />
                     </el-form-item>
                </el-col>
                <el-col :span="24">
                     <el-form-item label="备注">
                        <el-input v-model="form.description" type="textarea" :rows="2" placeholder="可选备注信息" />
                     </el-form-item>
                </el-col>
            </el-row>
        </div>
        
        <!-- 更多信息（卡片背景） -->
        <div class="more-info-box">
            <div class="info-title">
                <el-icon><Setting /></el-icon> 权限绑定
            </div>
            <el-row :gutter="20">
                <el-col :span="24">
                    <el-form-item label="绑定角色">
                         <el-select
                            v-model="form.roleIds"
                            multiple
                            filterable
                            collapse-tags
                            collapse-tags-tooltip
                            placeholder="可选，绑定到该节点的角色"
                            style="width: 100%"
                            :loading="rolesLoading"
                         >
                            <el-option
                                v-for="r in roleOptions"
                                :key="r.id"
                                :label="`${r.name} (${r.code})`"
                                :value="r.id"
                            />
                         </el-select>
                    </el-form-item>
                </el-col>
                <el-col :span="24">
                     <el-form-item label="管理员">
                        <div class="user-binding-container" style="width: 100%">
                            <div class="filter-bar" style="display: flex; gap: 8px; margin-bottom: 8px;">
                                <el-select 
                                    v-model="userFilterRole" 
                                    placeholder="按角色筛选" 
                                    clearable 
                                    style="width: 160px"
                                    @change="handleUserFilterRoleChange"
                                    size="small"
                                >
                                    <el-option
                                        v-for="r in roleOptions"
                                        :key="r.id"
                                        :label="r.name"
                                        :value="r.id"
                                    />
                                </el-select>
                                <el-checkbox v-model="form.inheritUser" label="继承到子节点" size="small" />
                            </div>
                            <el-select
                                v-model="form.userIds"
                                multiple
                                filterable
                                remote
                                :remote-method="handleUsersRemoteSearch"
                                :reserve-keyword="false"
                                collapse-tags
                                collapse-tags-tooltip
                                placeholder="可选，绑定到该节点的具体用户"
                                style="width: 100%"
                                :loading="usersLoading"
                            >
                                <el-option
                                    v-for="u in userOptions"
                                    :key="u.id"
                                    :label="formatUserDisplay(u, { fallback: `用户#${u.id}`, showUsernameWhenDifferent: true, includeIdWhenMissingName: true })"
                                    :value="u.id"
                                />
                            </el-select>
                        </div>
                     </el-form-item>
                </el-col>
            </el-row>
        </div>
      </el-form>
      <template #footer>
        <div class="dialog-footer-actions">
          <el-button @click="dialogVisible = false">取消</el-button>
          <el-button type="primary" @click="handleSave" :loading="saving" class="save-btn">确定保存</el-button>
        </div>
      </template>
    </el-dialog>

    <!-- Add Device Dialog -->
    <el-dialog v-model="deviceDialogVisible" title="添加设备" :width="isMobile ? '90%' : '500px'" append-to-body>
        <el-form :model="deviceForm" :label-width="isMobile ? '70px' : '80px'">
            <el-form-item label="选择设备">
                 <el-select 
                    v-model="deviceForm.deviceId" 
                    placeholder="请输入名称或IP搜索设备" 
                    filterable 
                    remote
                    :remote-method="handleDeviceRemoteSearch"
                    :loading="deviceSearchLoading"
                    style="width: 100%"
                 >
                    <el-option 
                        v-for="d in deviceOptions" 
                        :key="d.id" 
                        :label="`${d.device_name || d.name || '未知设备'} (${d.ipv4 || '-'})`" 
                        :value="d.id" 
                    />
                 </el-select>
            </el-form-item>
        </el-form>
        <template #footer>
            <el-button @click="deviceDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="confirmAddDevice" :loading="deviceSaving">确定</el-button>
        </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, reactive, nextTick, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
    Plus, Edit, Delete, Search, Refresh, Sort, 
    School, OfficeBuilding, House, Location,
    CopyDocument, Warning, ArrowDown, User, Monitor, Lock,
    Menu, Setting, Key, Reading, Management, Place, ArrowLeft
} from '@element-plus/icons-vue'
import axios from '@/axios/axios'
import { homeDataStore } from '@/components/home/home/data'
import { useDeviceStore } from '@/components/DeviceList/store'
import { getDeviceStatusTagType, getDeviceStatusText } from '@/components/DeviceList/deviceStatus'
import { formatUserDisplay } from '@/utils/userDisplay'

// --- State ---
const filterText = ref('')
const treeRef = ref(null)
const currentNode = ref(null)
const loading = ref(false)
const detailLoading = ref(false)
const globalLoading = computed(() => loading.value || detailLoading.value)
const saving = ref(false)
const isExpandAll = ref(true)
const store = homeDataStore()
const deviceStore = useDeviceStore()
store.syncAuthFromToken()
const nowTick = ref(Date.now())
let nowTimer = null

// Mobile Logic
const isMobile = ref(false)
const showMobileDetail = ref(false)
let mobileMediaQuery = null
let mobileMediaListener = null

// Dialogs
const dialogVisible = ref(false)
const dialogTitle = ref('新建位置')
const formType = ref('create')
const formRef = ref(null)
const isRoot = ref(false)
const currentParent = ref(null)

const deviceDialogVisible = ref(false)
const deviceForm = reactive({ deviceId: null })
const deviceOptions = ref([])
const deviceSearchLoading = ref(false)
const deviceSaving = ref(false)

const userFilterRole = ref(null)

// Form Data
const form = reactive({
    id: null,
    label: '',
    type: 'building',
    code: '',
    address: '',
    description: '',
    status: true,
    roleIds: [],
    userIds: [],
    inheritUser: false
})

const rules = {
    label: [{ required: true, message: '请输入名称', trigger: 'blur' }],
    type: [{ required: true, message: '请选择类型', trigger: 'change' }]
}

// Data
const defaultProps = {
  children: 'children',
  label: 'label',
}

const locationData = ref([])

const deviceList = ref([])

const roleOptions = ref([])
const rolesLoading = ref(false)
const userOptions = ref([])
const usersLoading = ref(false)
const usersQuery = ref('')

// --- Watchers ---
watch(filterText, (val) => {
  treeRef.value?.filter(val)
})

// --- Computed ---
const breadcrumbList = computed(() => {
    if (!currentNode.value) return []
    const list = []
    let node = treeRef.value.getNode(currentNode.value.id)
    while(node && node.level > 0) {
        list.unshift(node.label)
        node = node.parent
    }
    return list
})

const canAdd = computed(() => Boolean(store.isSuper) || (Array.isArray(store.permissions) && store.permissions.includes('sys:location:add')))
const canEdit = computed(() => Boolean(store.isSuper) || (Array.isArray(store.permissions) && store.permissions.includes('sys:location:edit')))
const canDel = computed(() => Boolean(store.isSuper) || (Array.isArray(store.permissions) && store.permissions.includes('sys:location:del')))

const canBindDevice = computed(() => {
    if (!currentNode.value) return false
    // restrict broad types
    const broadTypes = ['school', 'campus', 'department']
    return !broadTypes.includes(currentNode.value.type)
})

const roleLabelById = computed(() => {
    const m = new Map()
    for (const r of roleOptions.value || []) {
        const id = Number(r?.id)
        if (!Number.isNaN(id)) m.set(id, `${r?.name || r?.code || id}`)
    }
    return m
})

const userLabelById = computed(() => {
    const m = new Map()
    for (const u of userOptions.value || []) {
        const id = Number(u?.id)
        if (!Number.isNaN(id)) m.set(id, formatUserDisplay(u, { fallback: `用户#${id}`, showUsernameWhenDifferent: true, includeIdWhenMissingName: true }))
    }
    return m
})

const currentNodeRoleLabels = computed(() => {
    const ids = Array.isArray(currentNode.value?.roleIds) ? currentNode.value.roleIds : []
    return ids.map(id => roleLabelById.value.get(Number(id)) || `#${id}`)
})

const currentNodeUserLabels = computed(() => {
    const users = Array.isArray(currentNode.value?.users) ? currentNode.value.users : []
    if (users.length) {
        return users.map(u => formatUserDisplay(u, {
            fallback: `用户#${u?.id ?? '-'}`,
            showUsernameWhenDifferent: true,
            includeIdWhenMissingName: true
        }))
    }
    const ids = Array.isArray(currentNode.value?.userIds) ? currentNode.value.userIds : []
    return ids.map(id => userLabelById.value.get(Number(id)) || `#${id}`)
})

// --- Methods ---

const filterNode = (value, data) => {
  if (!value) return true
  const lowerValue = String(value || '').toLowerCase()
  return String(data?.label || '').toLowerCase().includes(lowerValue) || 
         (data?.code && String(data.code).toLowerCase().includes(lowerValue))
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

const handleNodeClick = async (data) => {
    detailLoading.value = true
    currentNode.value = data
    if (isMobile.value) {
        showMobileDetail.value = true
    }
    ensureUsersByIds(currentNode.value?.userIds)
    
    // Fetch real devices
    try {
        const res = await axios.get('/api/v1/user/device/get', { 
            params: { 
                location_node_id: data.id,
                page: 1,
                page_size: 100
            } 
        })
        deviceList.value = res.data || []
    } catch {
        deviceList.value = []
    } finally {
        // Simulate fetching delay
        setTimeout(() => {
            detailLoading.value = false
        }, 300)
    }
}

const handleCommand = (command) => {
    if (command === 'add') append(currentNode.value)
    else if (command === 'copy') handleCopy(currentNode.value)
    else if (command === 'delete') remove(currentNode.value)
}

// Icons & Styles
const getTypeIcon = (type) => {
    const map = { school: School, campus: Place, department: Management, building: OfficeBuilding, floor: House, classroom: Reading, room: Location }
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

const getTypeTagType = (type) => {
    const map = { campus: 'primary', building: 'warning', floor: 'success', room: 'info' }
    return map[type] || 'info'
}

const formatDate = (dateStr) => {
    if(!dateStr) return '-'
    return new Date(dateStr).toLocaleString()
}

const fetchTree = async (options = {}) => {
    const silent = Boolean(options.silent)
    if (!silent) loading.value = true
    try {
        const res = await axios.get('/api/v1/locations/tree')
        const payload = res?.data || {}
        if (payload?.code !== 200) {
            if (!silent) ElMessage.error(payload?.message || '获取位置树失败')
            return
        }
        locationData.value = Array.isArray(payload?.data) ? payload.data : []
    } catch (e) {
        if (!silent) ElMessage.error(e?.response?.data?.message || e?.message || '获取位置树失败')
    } finally {
        if (!silent) loading.value = false
    }
}

// Toolbar Actions
const handleRefresh = () => {
    fetchTree()
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
    if (!canAdd.value) {
        ElMessage.warning('无权限新增位置')
        return
    }
    isRoot.value = true
    currentParent.value = null
    formType.value = 'create'
    dialogTitle.value = '新建节点'
    resetForm()
    form.type = 'campus'
    dialogVisible.value = true
}

const append = (data) => {
    if (!canAdd.value) {
        ElMessage.warning('无权限新增位置')
        return
    }
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
    dialogVisible.value = true
}

const handleEdit = (data) => {
    if (!canEdit.value) {
        ElMessage.warning('无权限编辑位置')
        return
    }
    isRoot.value = !data.parent_id
    currentParent.value = null
    formType.value = 'edit'
    dialogTitle.value = `编辑 [${data.label}]`
    
    // Fill form
    Object.assign(form, data)
    form.status = data.status !== false
    form.roleIds = Array.isArray(data?.roleIds) ? data.roleIds.slice() : []
    form.userIds = Array.isArray(data?.userIds) ? data.userIds.slice() : []
    
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
    if (!canDel.value) {
        ElMessage.warning('无权限删除位置')
        return
    }
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
        saving.value = true
        axios.delete(`/api/v1/locations/${data.id}`).then((res) => {
            const payload = res?.data || {}
            if (payload?.code === 200) {
                if (currentNode.value?.id === data.id) currentNode.value = null
                fetchTree({ silent: true })
                ElMessage.success('删除成功')
                return
            }
            ElMessage.error(payload?.message || '删除失败')
        }).catch((e) => {
            ElMessage.error(e?.response?.data?.message || e?.message || '删除失败')
        }).finally(() => {
            saving.value = false
        })
    }).catch(() => {})
}

const handleSave = async () => {
    if (!formRef.value) return
    try {
        await formRef.value.validate()
    } catch {
        return
    }

    saving.value = true
    try {
        if (formType.value === 'create') {
            if (!canAdd.value) {
                ElMessage.warning('无权限新增位置')
                return
            }
            const payload = {
                parent_id: currentParent.value?.id ?? null,
                label: form.label,
                type: form.type,
                address: form.address,
                description: form.description,
                status: form.status,
                roleIds: form.roleIds,
                userIds: form.userIds,
                inherit_users: form.inheritUser
            }
            const res = await axios.post('/api/v1/locations/', payload)
            const out = res?.data || {}
            if (out?.code !== 200) {
                ElMessage.error(out?.message || '创建失败')
                return
            }
            ElMessage.success('创建成功')
            dialogVisible.value = false
            await fetchTree({ silent: true })
            if (currentParent.value?.id) {
                nextTick(() => {
                    const node = treeRef.value?.getNode(currentParent.value?.id)
                    if (node) node.expanded = true
                })
            }
            return
        }

        if (!canEdit.value) {
            ElMessage.warning('无权限编辑位置')
            return
        }
        const updatePayload = {
            label: form.label,
            type: form.type,
            address: form.address,
            description: form.description,
            status: form.status,
            roleIds: form.roleIds,
            userIds: form.userIds,
            inherit_users: form.inheritUser
        }
        const res = await axios.put(`/api/v1/locations/${form.id}`, updatePayload)
        const out = res?.data || {}
        if (out?.code !== 200) {
            ElMessage.error(out?.message || '更新失败')
            return
        }
        ElMessage.success('更新成功')
        dialogVisible.value = false
        await fetchTree({ silent: true })
        if (currentNode.value?.id === form.id && out?.data) {
            Object.assign(currentNode.value, out.data)
        }
    } catch (e) {
        ElMessage.error(e?.response?.data?.message || e?.message || '保存失败')
    } finally {
        saving.value = false
    }
}

const resetForm = () => {
    form.id = null
    form.label = ''
    form.code = ''
    form.address = ''
    form.description = ''
    form.status = true
    form.roleIds = []
    form.userIds = []
    form.inheritUser = false
    userFilterRole.value = null
    if(formRef.value) formRef.value.resetFields()
}

const fetchRoleOptions = async () => {
    if (!canAdd.value && !canEdit.value) return
    rolesLoading.value = true
    try {
        const res = await axios.get('/api/v1/locations/bind/roles')
        const out = res?.data || {}
        if (out?.code === 200) {
            roleOptions.value = Array.isArray(out?.data) ? out.data : []
        }
    } catch {}
    finally { rolesLoading.value = false }
}

const mergeUserOptions = (items) => {
    const next = Array.isArray(items) ? items : []
    const byId = new Map()
    for (const u of userOptions.value || []) {
        const id = Number(u?.id)
        if (!Number.isNaN(id)) byId.set(id, u)
    }
    for (const u of next) {
        const id = Number(u?.id)
        if (!Number.isNaN(id)) byId.set(id, u)
    }
    userOptions.value = Array.from(byId.values())
}

const ensureUsersByIds = async (ids) => {
    const list = Array.isArray(ids) ? ids.map(v => Number(v)).filter(v => !Number.isNaN(v)) : []
    if (!list.length) return
    const need = []
    const existing = new Set((userOptions.value || []).map(u => Number(u?.id)).filter(v => !Number.isNaN(v)))
    for (const id of list) {
        if (!existing.has(id)) need.push(id)
    }
    if (!need.length) return
    usersLoading.value = true
    try {
        const res = await axios.get('/api/v1/locations/bind/users/by_ids', { params: { ids: need } })
        const out = res?.data || {}
        if (out?.code === 200) mergeUserOptions(out?.data)
    } catch {}
    finally { usersLoading.value = false }
}

const fetchUsers = async ({ q } = {}) => {
    if (!canAdd.value && !canEdit.value) return
    usersLoading.value = true
    try {
        const params = { q: String(q ?? '') || '', page: 1, page_size: 50 }
        if (userFilterRole.value) params.role_id = userFilterRole.value
        const res = await axios.get('/api/v1/locations/bind/users', { params })
        const out = res?.data || {}
        if (out?.code === 200) mergeUserOptions(out?.data)
    } catch {}
    finally { usersLoading.value = false }
}

const handleUserFilterRoleChange = async () => {
    // Keep only selected users in options to avoid display issues
    const selected = new Set((form.userIds || []).map(Number))
    userOptions.value = userOptions.value.filter(u => selected.has(Number(u.id)))
    await fetchUsers({ q: usersQuery.value })
}

const handleUsersRemoteSearch = async (query) => {
    usersQuery.value = String(query ?? '')
    await fetchUsers({ q: usersQuery.value })
}

watch(dialogVisible, async (visible) => {
    if (!visible) return
    await fetchRoleOptions()
    await ensureUsersByIds(form.userIds)
})

// Drag & Drop
const allowDrag = () => canEdit.value
const allowDrop = (draggingNode, dropNode) => {
    if (!canEdit.value) return false
    const dragId = draggingNode?.data?.id
    if (!dragId) return false
    let p = dropNode
    while (p) {
        if (p?.data?.id === dragId) return false
        p = p.parent
    }
    return true
}
const handleDrop = async (draggingNode, dropNode, dropType) => {
    if (!canEdit.value) return
    const dragId = draggingNode?.data?.id
    if (!dragId) return
    const dropData = dropNode?.data || {}
    const nextParentId = dropType === 'inner' ? dropData?.id : (dropData?.parent_id ?? null)

    saving.value = true
    try {
        const res = await axios.post(`/api/v1/locations/${dragId}/move`, { parent_id: nextParentId })
        const out = res?.data || {}
        if (out?.code !== 200) {
            ElMessage.error(out?.message || '移动失败')
            return
        }
        ElMessage.success('已移动位置')
        await fetchTree({ silent: true })
    } catch (e) {
        ElMessage.error(e?.response?.data?.message || e?.message || '移动失败')
    } finally {
        saving.value = false
    }
}

const handleAddDevice = () => {
    if (!currentNode.value) return
    deviceForm.deviceId = null
    deviceOptions.value = []
    deviceDialogVisible.value = true
    fetchDeviceOptions()
}

const fetchDeviceOptions = async (query = '') => {
    deviceSearchLoading.value = true
    try {
        const res = await axios.get('/api/v1/user/device/get', { params: { search: query, page: 1, page_size: 100 } })
        const data = res?.data || []
        deviceOptions.value = Array.isArray(data) ? data : []
    } catch {
        deviceOptions.value = []
    } finally {
        deviceSearchLoading.value = false
    }
}

const handleDeviceRemoteSearch = (query) => {
    fetchDeviceOptions(query)
}

const confirmAddDevice = async () => {
    if (!deviceForm.deviceId) {
        ElMessage.warning('请选择设备')
        return
    }
    
    // Check if device already in list
    const exists = deviceList.value.some(d => d.id === deviceForm.deviceId)
    if (exists) {
        ElMessage.warning('该设备已在此位置')
        return
    }

    deviceSaving.value = true
    try {
        await axios.post(`/api/v1/locations/${currentNode.value.id}/devices`, {
            device_ids: [deviceForm.deviceId]
        })
        ElMessage.success('设备添加成功')
        deviceDialogVisible.value = false
        // Refresh detail to show new device
        await handleNodeClick(currentNode.value)
    } catch (e) {
        ElMessage.error(e?.response?.data?.message || '添加失败')
    } finally {
        deviceSaving.value = false
    }
}

const handleRemoveDevice = (row) => {
    ElMessageBox.confirm(
        `确定要移除设备 [${row.name || row.device_name}] 吗？`,
        '移除确认',
        {
            confirmButtonText: '移除',
            cancelButtonText: '取消',
            type: 'warning'
        }
    ).then(async () => {
        try {
            await axios.delete(`/api/v1/locations/${currentNode.value.id}/devices`, {
                data: { device_ids: [row.id] }
            })
            ElMessage.success('移除成功')
            await handleNodeClick(currentNode.value)
        } catch (e) {
            ElMessage.error(e?.response?.data?.message || '移除失败')
        }
    })
}

const getDeviceStatusModel = (row) => {
    if (!row) return {}
    const found = deviceStore.data.find(d => d.id === row.id)
    return found || row
}

const handleMobileBack = () => {
    showMobileDetail.value = false
    currentNode.value = null
}

onMounted(async () => {
    store.syncAuthFromToken()
    await store.fetchPermissions({ force: false })
    await fetchTree()
    deviceStore.startRealtime()
    
    // Mobile Check
    mobileMediaQuery = window.matchMedia('(max-width: 768px)')
    mobileMediaListener = () => {
        isMobile.value = mobileMediaQuery.matches
        if (!isMobile.value) showMobileDetail.value = false
    }
    mobileMediaListener()
    if (mobileMediaQuery.addEventListener) {
        mobileMediaQuery.addEventListener('change', mobileMediaListener)
    } else {
        mobileMediaQuery.addListener(mobileMediaListener)
    }

    // Timer
    nowTimer = window.setInterval(() => {
        nowTick.value = Date.now()
    }, 1000)
})

onBeforeUnmount(() => {
    if (mobileMediaQuery && mobileMediaListener) {
        if (mobileMediaQuery.removeEventListener) {
            mobileMediaQuery.removeEventListener('change', mobileMediaListener)
        } else {
            mobileMediaQuery.removeListener(mobileMediaListener)
        }
    }
    
    if (nowTimer) {
        clearInterval(nowTimer)
        nowTimer = null
    }
    deviceStore.stopRealtime()
})

</script>

<style scoped>
.location-container {
    height: 100%;
    display: flex;
    background-color: #f0f2f5;
    padding: 16px;
    gap: 16px;
    box-sizing: border-box;
}

/* Sidebar */
.sidebar-card {
    width: 320px;
    background: #fff;
    border-radius: 8px;
    display: flex;
    flex-direction: column;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    overflow: hidden;
}

.sidebar-header {
    padding: 16px;
    border-bottom: 1px solid #f0f0f0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.sidebar-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
}

.sidebar-action-area {
    padding: 16px 16px 0 16px;
}

.full-width-btn {
    width: 100%;
    border-style: dashed;
}

.filter-wrapper {
    padding: 12px 16px;
}

.tree-content {
    flex: 1;
    overflow-y: auto;
    padding: 0 8px 16px 8px;
}

.custom-tree-node {
    flex: 1;
    display: flex;
    align-items: center;
    font-size: 14px;
    padding-right: 8px;
    overflow: hidden;
}

.node-main {
    display: flex;
    align-items: center;
    width: 100%;
    overflow: hidden;
}

.node-icon {
    margin-right: 8px;
    flex-shrink: 0;
}

.node-label {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.node-highlight {
    color: var(--el-color-primary);
    font-weight: bold;
}

.status-badge {
    margin-left: auto;
    font-size: 10px;
    padding: 1px 4px;
    border-radius: 4px;
    flex-shrink: 0;
}
.status-badge.off {
    background: #fef0f0;
    color: #f56c6c;
}

/* Main Content */
.main-content {
    flex: 1;
    background: #fff;
    border-radius: 8px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.content-wrapper {
    height: 100%;
    display: flex;
    flex-direction: column;
    overflow-y: auto;
    padding: 24px;
}

/* Header */
.content-header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    margin-bottom: 24px;
}

.breadcrumb-area {
    margin-bottom: 12px;
}

.title-row {
    display: flex;
    align-items: center;
}

.node-title {
    margin: 0;
    font-size: 24px;
    font-weight: 600;
    color: #1d2129;
    line-height: 1.2;
}

.ml-2 { margin-left: 8px; }
.ml-3 { margin-left: 12px; }

/* Stats Row */
.stats-row {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 16px;
    margin-bottom: 24px;
}

.stat-card {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 16px;
    display: flex;
    align-items: center;
    transition: all 0.3s;
}
.stat-card:hover {
    background: #fff;
    box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    transform: translateY(-2px);
}

.stat-icon {
    width: 48px;
    height: 48px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    color: #fff;
    margin-right: 16px;
}
.bg-blue { background: linear-gradient(135deg, #409eff, #79bbff); }
.bg-green { background: linear-gradient(135deg, #67c23a, #95d475); }
.bg-purple { background: linear-gradient(135deg, #722ed1, #b37feb); }
.bg-orange { background: linear-gradient(135deg, #e6a23c, #f3d19e); }

.stat-info {
    display: flex;
    flex-direction: column;
}
.stat-label {
    font-size: 13px;
    color: #909399;
    margin-bottom: 4px;
}
.stat-value {
    font-size: 20px;
    font-weight: 700;
    color: #303133;
}

/* Details Grid */
.details-grid {
    display: flex;
    gap: 24px;
    flex: 1;
}

.info-section {
    flex: 1;
    min-width: 0;
}

.device-section {
    flex: 1.5;
    min-width: 0;
    display: flex;
    flex-direction: column;
}

.section-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 16px;
    padding-bottom: 8px;
    border-bottom: 1px solid #f0f0f0;
}

.section-title {
    font-size: 16px;
    font-weight: 600;
    color: #303133;
    position: relative;
    padding-left: 12px;
}
.section-title::before {
    content: '';
    position: absolute;
    left: 0;
    top: 50%;
    transform: translateY(-50%);
    width: 4px;
    height: 16px;
    background: #409eff;
    border-radius: 2px;
}

.user-info, .phone-text {
    display: flex;
    align-items: center;
    gap: 8px;
}

.empty-placeholder {
    height: 100%;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #909399;
    background: #fff;
    border-radius: 8px;
}

/* Responsive */
@media (max-width: 1200px) {
    .stats-row {
        grid-template-columns: repeat(2, 1fr);
    }
    .details-grid {
        flex-direction: column;
    }
}

@media (max-width: 768px) {
    .location-container.is-mobile {
        padding: 0;
        display: block;
        background: #fff;
    }

    .sidebar-card, .main-content {
        width: 100%;
        height: 100%;
        border-radius: 0;
        box-shadow: none;
        border: none;
    }
    
    .stats-row {
        grid-template-columns: 1fr;
        gap: 12px;
    }
    
    .mobile-back-row {
        margin-bottom: 12px;
        border-bottom: 1px solid #f0f0f0;
        padding-bottom: 8px;
        width: 100%;
    }
    
    .back-btn {
        font-size: 16px;
        padding-left: 0;
        color: #606266;
    }

    .content-wrapper {
        padding: 16px;
    }
    
    .content-header {
        flex-direction: column;
        gap: 12px;
    }
    
    .header-right {
        width: 100%;
        display: flex;
        justify-content: flex-end;
    }
    
    .node-title {
        font-size: 20px;
    }
    
    /* Enhance touch targets */
    .custom-tree-node {
        padding: 8px 0;
    }
    :deep(.el-tree-node__content) {
        height: 44px;
    }

    /* Dialog fixes for mobile */
    .location-dialog .el-dialog__body {
        padding: 16px !important;
        max-height: 70vh;
        overflow-y: auto;
    }
    
    .filter-bar {
        flex-direction: column;
        align-items: flex-start;
    }
}
</style>

<style>
/* Global styles for Dialog (append-to-body) */
.location-dialog {
    border-radius: 12px !important;
    overflow: hidden;
    box-shadow: 0 12px 32px 4px rgba(0, 0, 0, 0.08), 0 8px 20px rgba(0, 0, 0, 0.04) !important;
}
.location-dialog .el-dialog__header {
    margin-right: 0;
    padding: 20px 24px;
    background: #fff;
    border-bottom: 1px solid #f0f0f0;
}
.location-dialog .el-dialog__title {
    font-weight: 600;
    font-size: 18px;
    color: #1d2129;
}
.location-dialog .el-dialog__body {
    padding: 24px !important;
}
.location-dialog .el-dialog__footer {
    padding: 16px 24px;
    border-top: 1px solid #f0f0f0;
    background: #fcfcfc;
}

/* Form Styles */
.location-form .el-form-item__label {
    font-weight: 500;
}
.location-form .el-input__wrapper {
    box-shadow: 0 0 0 1px #dcdfe6 inset;
}
.location-form .el-input__wrapper:hover {
    box-shadow: 0 0 0 1px #c0c4cc inset;
}
.location-form .el-input__wrapper.is-focus {
    box-shadow: 0 0 0 1px #409eff inset !important; 
}

.code-input .el-input__wrapper {
    background-color: #f5f7fa;
}

.form-section {
    padding: 0 4px;
}

.more-info-box {
    background: #f8f9fa;
    border-radius: 8px;
    padding: 20px 20px 4px 20px;
    margin-top: 24px;
    border: 1px solid #eee;
}

.info-title {
    font-size: 14px;
    font-weight: 600;
    color: #606266;
    margin-bottom: 16px;
    display: flex;
    align-items: center;
    gap: 8px;
}

.dialog-footer-actions {
    display: flex;
    justify-content: flex-end;
    gap: 12px;
}

.save-btn {
    padding: 8px 24px;
    font-weight: 500;
}

.mt-3 {
    margin-top: 12px;
}
</style>
