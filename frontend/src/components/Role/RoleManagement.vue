<template>
  <div class="rbac-container">
    <!-- 顶部标题与切换卡 -->
    <div class="rbac-header">
      <div class="page-title">
        <el-icon class="mr-2"><Key /></el-icon>
        <span>角色与权限管理</span>
        <el-tooltip content="管理系统角色、权限点及关联关系" placement="right">
          <el-icon class="info-icon"><InfoFilled /></el-icon>
        </el-tooltip>
      </div>
      
      <div ref="tabSwitcherRef" class="tab-switcher">
        <div 
          class="tab-item" 
          ref="tabRoleRef"
          :class="{ active: activeTab === 'role' }"
          @click="activeTab = 'role'"
        >
          <el-icon><Avatar /></el-icon> 角色管理
        </div>
        <div 
          class="tab-item" 
          ref="tabPermissionRef"
          :class="{ active: activeTab === 'permission' }"
          @click="activeTab = 'permission'"
        >
          <el-icon><Lock /></el-icon> 权限管理
        </div>
        <div class="tab-indicator" :style="indicatorStyle"></div>
      </div>
    </div>

    <!-- 内容区域 -->
    <div class="rbac-content">
      <!-- 角色管理视图 -->
        <div v-show="activeTab === 'role'" class="view-container role-view">
          <!-- 左侧：角色列表 -->
          <div class="left-panel" v-show="!isMobile || !showMobileDetail">
            <div class="panel-header">
              <span class="panel-title">角色列表</span>
              <el-button type="primary" size="small" circle :icon="Plus" @click="handleCreateRole" />
            </div>
            
            <div class="role-list" v-loading="roleLoading">
              <div 
                v-for="role in roleTableData" 
                :key="role.id"
                class="role-item"
                :class="{ active: currentRole?.id === role.id }"
                @click="handleRoleClick(role)"
              >
                <div class="role-icon">
                  <el-icon><UserFilled /></el-icon>
                </div>
                <div class="role-info">
                  <div class="role-name">{{ role.name }}</div>
                  <div class="role-meta">
                    <span class="code">{{ role.code }}</span>
                    <el-tag v-if="role.is_default" size="small" type="success" effect="dark">默认</el-tag>
                  </div>
                </div>
                <div class="role-actions">
                  <el-dropdown trigger="click" @command="(cmd) => handleRoleCommand(cmd, role)">
                    <el-icon class="action-icon"><MoreFilled /></el-icon>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item v-if="!role.is_default && role.id !== 'new'" command="default">设为默认</el-dropdown-item>
                        <el-dropdown-item command="copy">复制角色</el-dropdown-item>
                        <el-dropdown-item command="delete" divided style="color: #f56c6c">删除角色</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
            </div>
          </div>

          <!-- 右侧：角色详情与权限配置 -->
          <div class="right-panel" v-if="currentRole" v-show="!isMobile || showMobileDetail">
            <div class="panel-header">
              <div style="display:flex;align-items:center;">
                <el-button v-if="isMobile" link :icon="Back" @click="handleBackToList" style="margin-right:8px;font-size:18px;"></el-button>
                <span class="panel-title">角色配置: {{ currentRole.name }}</span>
              </div>
              <div class="header-actions">
                 <el-tag v-if="currentRole.is_default" type="success" effect="dark" class="mr-2">默认角色</el-tag>
                 <el-tag v-if="hasChanges" type="warning" effect="dark" class="mr-2">未保存</el-tag>
                 <el-button v-if="!currentRole.is_default && currentRole.id !== 'new'" @click="handleSetDefaultRole(currentRole)">设为默认</el-button>
                 <el-button type="primary" :loading="roleSaving" @click="saveCurrentRole">保存修改</el-button>
              </div>
            </div>

            <div class="panel-body custom-scrollbar">
              <!-- A. 基础信息 -->
              <div class="config-section">
                <div class="section-title">基础信息</div>
                <el-form :model="currentRoleForm" label-position="top" class="role-form">
                  <el-row :gutter="20">
                    <el-col :span="12">
                      <el-form-item label="角色名称">
                        <el-input v-model="currentRoleForm.name" placeholder="请输入角色名称" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="12">
                      <el-form-item label="角色编码">
                        <el-input v-model="currentRoleForm.code" placeholder="唯一标识，如: admin" :disabled="currentRole.id !== 'new'" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="24">
                      <el-form-item label="描述">
                        <el-input v-model="currentRoleForm.description" type="textarea" :rows="2" placeholder="角色职能描述..." />
                      </el-form-item>
                    </el-col>
                  </el-row>
                </el-form>
              </div>

              <div class="config-section">
                <div class="section-title">
                  <span>成员管理</span>
                  <el-button
                    type="primary"
                    size="small"
                    style="float: right;"
                    @click="openAddMembersDialog"
                    :disabled="currentRole.id === 'new'"
                  >
                    添加成员
                  </el-button>
                </div>

                <el-table :data="roleMembers" size="small" stripe v-loading="roleMembersLoading">
                  <el-table-column prop="username" label="用户名" min-width="160" />
                  <el-table-column prop="nickname" label="昵称" min-width="160" />
                  <el-table-column prop="email" label="邮箱" min-width="180" show-overflow-tooltip />
                  <el-table-column label="操作" width="120" fixed="right">
                    <template #default="{ row }">
                      <el-button type="danger" link @click="handleRemoveMember(row)" :disabled="currentRole.id === 'new'">
                        移除
                      </el-button>
                    </template>
                  </el-table-column>
                </el-table>
                <div class="pagination-container">
                  <el-pagination
                    v-model:current-page="roleMembersPage"
                    v-model:page-size="roleMembersPageSize"
                    :total="roleMembersTotal"
                    :page-sizes="[10, 20, 50, 100]"
                    layout="total, sizes, prev, pager, next, jumper"
                    small
                    background
                    @current-change="handleRoleMembersPageChange"
                    @size-change="handleRoleMembersPageSizeChange"
                  />
                </div>
              </div>

              <!-- B. 权限矩阵 -->
              <div class="config-section">
                <div class="section-title">
                  <span>功能权限</span>
                  <el-input 
                    v-model="permFilterText" 
                    placeholder="搜索权限..." 
                    prefix-icon="Search" 
                    size="small" 
                    style="width: 200px; float: right;" 
                    clearable
                  />
                </div>
                
                <div class="perm-matrix">
                   <div v-for="(group, groupName) in filteredPermissionGroups" :key="groupName" class="perm-group-card">
                      <div class="group-header">
                        <span class="group-name">{{ groupName }}</span>
                        <el-checkbox 
                          v-model="group.allChecked" 
                          :indeterminate="group.isIndeterminate"
                          @change="(val) => handleGroupCheckAll(val, group)"
                        >全选</el-checkbox>
                      </div>
                      <div class="group-items">
                        <div 
                          v-for="perm in group.items" 
                          :key="perm.id" 
                          class="perm-item"
                          :class="{ active: currentRolePermIds.includes(perm.id), child: perm._depth === 1, grandchild: perm._depth === 2 }"
                          @click="togglePerm(perm.id)"
                        >
                          <div class="perm-switch">
                            <el-switch 
                              :model-value="currentRolePermIds.includes(perm.id)"
                              @change="() => togglePerm(perm.id)"
                              :disabled="isGloballyDisabled(perm.code)"
                              size="small"
                            />
                          </div>
                          <div class="perm-label">
                            <div class="name">
                              <span>{{ perm.name }}</span>
                              <el-tag 
                                v-if="isGloballyDisabled(perm.code)" 
                                size="small" 
                                type="danger" 
                                style="margin-left:6px;"
                              >已全局禁用</el-tag>
                            </div>
                            <div class="code">{{ perm.code }}</div>
                          </div>
                        </div>
                      </div>
                   </div>
                   <el-empty v-if="Object.keys(filteredPermissionGroups).length === 0" description="未找到相关权限" />
                </div>
              </div>

              <!-- C. 数据权限 (模拟) -->
              <!-- <div class="config-section">
                <div class="section-title">数据权限</div>
                <el-form label-position="left" label-width="100px">
                  <el-form-item label="数据范围">
                    <el-select v-model="currentRoleForm.dataScope" placeholder="请选择">
                      <el-option label="全部数据" value="all" />
                      <el-option label="所在部门" value="dept" />
                      <el-option label="仅本人" value="self" />
                    </el-select>
                  </el-form-item>
                </el-form>
              </div> -->
            </div>
          </div>
          
          <div class="right-panel empty-state" v-else v-show="!isMobile">
            <el-empty description="请选择左侧角色进行配置" />
          </div>
        </div>

        <!-- 权限管理视图 -->
        <div v-show="activeTab === 'permission'" class="view-container perm-view">
           <!-- 左侧：权限树/列表 -->
           <div class="left-panel" v-show="!isMobile || !showMobileDetail">
           <div class="panel-header">
              <span class="panel-title">权限目录</span>
              <div>
                <el-button size="small" :loading="permSyncing" @click="handleSyncPermissions">一键同步</el-button>
                <el-button size="small" @click="fetchPermissionDirectory">刷新</el-button>
                <el-button type="primary" size="small" circle :icon="Plus" @click="handleCreatePerm" />
              </div>
            </div>
             <div class="search-bar">
               <el-input v-model="permListFilter" placeholder="搜索权限名称/编码" prefix-icon="Search" clearable />
             </div>
             <div class="perm-tree-list custom-scrollbar" v-loading="permissionLoading">
                <div v-for="(group, groupName) in filteredPermGroups" :key="groupName" class="perm-tree-group">
                  <div class="perm-tree-group-header">{{ groupName }}</div>
                  <div 
                    v-for="perm in group.items" 
                    :key="perm.id ?? perm.code"
                    class="perm-tree-item"
                    :class="{ active: currentPerm?.code === perm.code, child: perm._depth === 1, grandchild: perm._depth === 2 }"
                    @click="handlePermClick(perm)"
                  >
                    <el-icon class="item-icon"><Connection /></el-icon>
                    <div class="item-content">
                      <div class="item-title">
                        <span>{{ perm.name }}</span>
                        <el-tag 
                          v-if="isGloballyDisabled(perm.code)" 
                          size="small" 
                          type="danger" 
                          style="margin-left:6px;"
                        >已全局禁用</el-tag>
                      </div>
                      <div class="item-subtitle">{{ perm.code }}</div>
                    </div>
                    <div style="display:flex;align-items:center;gap:6px;">
                      <el-button
                        class="global-disable-btn"
                        size="small"
                        link
                        :type="isGloballyDisabled(perm.code) ? 'success' : 'danger'"
                        :loading="disabledSavingCode === String(perm.code || '').trim()"
                        @click.stop="toggleGlobalDisabledForPerm(perm.code)"
                      >
                        {{ isGloballyDisabled(perm.code) ? '启用' : '禁用' }}
                      </el-button>
                      <el-tag size="small" :type="perm.in_directory ? 'success' : 'info'">{{ perm.in_directory ? '系统' : '自定义' }}</el-tag>
                      <el-tag v-if="perm.exists === false" size="small" type="warning">未同步</el-tag>
                    </div>
                    <el-button 
                      v-if="perm.id && !perm.in_directory"
                      type="danger" 
                      link 
                      :icon="Delete" 
                      @click.stop="handlePermDelete(perm)" 
                      class="delete-btn"
                    />
                  </div>
                </div>
                <el-empty v-if="Object.keys(filteredPermGroups).length === 0" description="未找到相关权限" />
             </div>
           </div>

           <!-- 右侧：权限详情 -->
           <div class="right-panel" v-if="currentPerm" v-show="!isMobile || showMobileDetail">
              <div class="panel-header">
                <div style="display:flex;align-items:center;">
                  <el-button v-if="isMobile" link :icon="Back" @click="handleBackToList" style="margin-right:8px;font-size:18px;"></el-button>
                  <span class="panel-title">权限详情</span>
                </div>
                <el-button type="primary" :disabled="!currentPerm?.id" :loading="permSaving" @click="saveCurrentPerm">保存</el-button>
              </div>
              <div class="panel-body">
                <div class="config-section">
                  <el-form :model="currentPermForm" label-width="100px" class="perm-form">
                    <el-form-item label="权限名称" required>
                      <el-input v-model="currentPermForm.name" :disabled="!currentPerm?.id" />
                    </el-form-item>
                    <el-form-item label="权限编码" required>
                      <el-input v-model="currentPermForm.code" placeholder="例如: sys:user:view" :disabled="!currentPerm?.id || currentPerm?.in_directory" />
                    </el-form-item>
                    <el-form-item label="描述">
                      <el-input v-model="currentPermForm.description" type="textarea" :rows="3" :disabled="!currentPerm?.id" />
                    </el-form-item>
                    <el-form-item label="全局禁用">
                      <el-switch
                        :model-value="isGloballyDisabled(currentPermForm.code)"
                        :disabled="!currentPerm?.id"
                        @change="(val) => setGlobalDisabledForPerm(currentPermForm.code, val)"
                      />
                    </el-form-item>
                    <!-- <el-form-item label="类型">
                      <el-radio-group v-model="currentPermForm.type">
                        <el-radio label="menu">菜单</el-radio>
                        <el-radio label="button">按钮</el-radio>
                        <el-radio label="api">API</el-radio>
                      </el-radio-group>
                    </el-form-item> -->
                  </el-form>
                </div>
              </div>
           </div>
           
           <div class="right-panel empty-state" v-else v-show="!isMobile">
             <el-empty description="请选择或新建权限" />
           </div>
        </div>

        <div v-show="activeTab === 'distribution'" class="view-container distribution-view">
          <div class="distribution-container" v-loading="roleUsersLoading">
            <div class="distribution-header">
              <div class="distribution-title">角色人员分布</div>
              <el-button type="primary" :loading="roleUsersLoading" @click="fetchRoleUsers">刷新</el-button>
            </div>

            <div class="role-cards">
              <el-card v-for="role in roleUsersData" :key="role.id" class="role-card" shadow="hover">
                <template #header>
                  <div class="role-card-header">
                    <div class="role-card-name">{{ role.name }}</div>
                    <el-tag size="small" type="info">{{ (role.users || []).length }} 人</el-tag>
                  </div>
                </template>

                <div v-if="(role.users || []).length === 0" class="role-card-empty">
                  <el-empty description="暂无成员" :image-size="60" />
                </div>
                <div v-else class="role-user-tags">
                  <el-tag
                    v-for="u in role.users"
                    :key="u.id"
                    size="small"
                    effect="plain"
                    class="user-tag"
                  >
                    {{ u.nickname || u.username }}
                  </el-tag>
                </div>
              </el-card>
            </div>
          </div>
        </div>

        <el-dialog v-model="addMembersDialogVisible" title="添加成员" :width="isMobile ? '90%' : '560px'">
          <el-form label-width="90px">
            <el-form-item label="选择用户">
              <el-select
                v-model="selectedUserIds"
                multiple
                filterable
                remote
                :remote-method="handleAvailableUsersRemoteSearch"
                :reserve-keyword="false"
                collapse-tags
                collapse-tags-tooltip
                placeholder="请选择要添加的用户"
                style="width: 100%"
                :loading="availableUsersLoading"
              >
                <el-option
                  v-for="u in availableUsers"
                  :key="u.id"
                  :label="`${u.nickname || u.username} (${u.username})`"
                  :value="u.id"
                />
              </el-select>
            </el-form-item>
          </el-form>
          <template #footer>
            <el-button @click="addMembersDialogVisible = false">取消</el-button>
            <el-button type="primary" @click="handleAddMembers" :loading="roleMembersLoading">确定</el-button>
          </template>
        </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import axios from '@/axios/axios';
import { ElMessage, ElMessageBox } from 'element-plus';
import Cookies from 'js-cookie';
import { jwtDecode } from 'jwt-decode';
import { 
  Key, InfoFilled, Avatar, Lock, Plus, UserFilled, MoreFilled, 
  Search, Connection, Delete, User, Back
} from '@element-plus/icons-vue';

// --- State ---
const route = useRoute();
const router = useRouter();
const activeTab = ref('role');
const hasChanges = ref(false);

// --- Mobile Support ---
const isMobile = ref(false);
const showMobileDetail = ref(false);

const handleResize = () => {
  isMobile.value = window.innerWidth <= 768;
};

const handleRoleClick = (role) => {
  handleSelectRole(role);
  if (isMobile.value) {
    showMobileDetail.value = true;
  }
};

const handlePermClick = (perm) => {
  handleSelectPerm(perm);
  if (isMobile.value) {
    showMobileDetail.value = true;
  }
};

const handleBackToList = () => {
  showMobileDetail.value = false;
};


// --- Role State ---
const roleLoading = ref(false);
const roleSaving = ref(false);
const roleTableData = ref([]);
const currentRole = ref(null);
const currentRoleForm = reactive({ name: '', code: '', description: '', dataScope: 'all' });
const currentRolePermIds = ref([]); // 当前角色选中的权限ID集合

// --- Permission State ---
const permissionLoading = ref(false);
const permSaving = ref(false);
const allPermissions = ref([]); // 所有的权限列表
const permissionDirectory = ref([]);
const permSyncing = ref(false);
const currentPerm = ref(null);
const currentPermForm = reactive({ name: '', code: '', description: '', type: 'button' });
const permFilterText = ref(''); // 角色详情里的权限搜索
const permListFilter = ref(''); // 权限管理里的列表搜索
const disabledPermCodes = ref([]); // 被全局禁用的权限编码集合
const disabledSavingCode = ref('');

const roleUsersLoading = ref(false);
const roleUsersData = ref([]);

const roleMembersLoading = ref(false);
const roleMembers = ref([]);
const roleMembersPage = ref(1);
const roleMembersPageSize = ref(20);
const roleMembersTotal = ref(0);

const addMembersDialogVisible = ref(false);
const availableUsersLoading = ref(false);
const availableUsers = ref([]);
const selectedUserIds = ref([]);
const availableUsersQuery = ref('');

const currentUserId = ref(null);

// --- Computed ---

const permissionDepsByCode = {
  'sys:location:del': ['sys:location:view'],
  'sys:device:add': ['sys:device:list'],
  'sys:device:edit': ['sys:device:list'],
  'sys:device:del': ['sys:device:list'],
  'sys:device:audit': ['sys:device:list'],
  'sys:user:manage': ['sys:user:view'],
  'sys:user:import': ['sys:user:manage'],
  'sys:config:edit': ['sys:config:view'],
  'sys:repair:create': ['sys:repair:view'],
  'sys:repair:handle': ['sys:repair:view'],
  'sys:repair:manage': ['sys:repair:view', 'sys:repair:handle'],
  'sys:role:manage': ['sys:role:view'],
  'sys:menu:manage': ['sys:menu:view'],
};

const normalizePermCode = (code) => String(code || '').trim();

const getPermModuleKey = (code) => {
  const parts = normalizePermCode(code).split(':').filter(Boolean);
  if (parts.length >= 2 && parts[0] === 'sys') return parts[1];
  return parts[0] || '';
};

const moduleNameMap = {
  auth: '认证授权',
  email: '认证授权',
  dashboard: '系统概览',
  monitor: '监控告警',
  alert: '监控告警',
  message: '消息中心',
  location: '位置管理',
  device: '设备管理',
  ssh: '设备管理',
  user: '用户管理',
  config: '系统配置',
  notify: '通知',
  repair: '工单系统',
  role: '角色权限',
  menu: '菜单管理',
};

const getPermGroupName = (code) => {
  const moduleKey = getPermModuleKey(code);
  return moduleNameMap[moduleKey] || (moduleKey ? moduleKey.toUpperCase() : '其他');
};

const getPermActionKey = (code) => {
  const parts = normalizePermCode(code).split(':').filter(Boolean);
  const action = parts[parts.length - 1] || '';
  const priority = {
    view: 0,
    list: 0,
    login: 0,
    register: 1,
    verify: 1,
    create: 2,
    add: 2,
    edit: 3,
    del: 4,
    connect: 5,
    handle: 6,
    manage: 7,
    global: 8,
  };
  return { action, priority: priority[action] ?? 50 };
};

const getPermDepth = (code) => {
  const { action } = getPermActionKey(code);
  if (action === 'view' || action === 'list') return 0;
  if (action === 'manage') return 2;
  return 1;
};

const expandPermCodes = (codes) => {
  const selected = new Set((codes || []).map(normalizePermCode).filter(Boolean));
  let changed = true;
  while (changed) {
    changed = false;
    for (const code of Array.from(selected)) {
      const deps = permissionDepsByCode[code] || [];
      for (const dep of deps) {
        const depNorm = normalizePermCode(dep);
        if (depNorm && !selected.has(depNorm)) {
          selected.add(depNorm);
          changed = true;
        }
      }
    }
  }
  return Array.from(selected);
};

const buildStableSelectionAfterRemoval = (selectedCodes) => {
  const selected = new Set((selectedCodes || []).map(normalizePermCode).filter(Boolean));
  let changed = true;
  while (changed) {
    changed = false;
    for (const code of Array.from(selected)) {
      const deps = permissionDepsByCode[code] || [];
      const ok = deps.every(d => selected.has(normalizePermCode(d)));
      if (!ok) {
        selected.delete(code);
        changed = true;
      }
    }
  }
  return Array.from(selected);
};

const permIdByCode = computed(() => {
  const map = new Map();
  (allPermissions.value || []).forEach(p => {
    const code = normalizePermCode(p.code);
    if (code) map.set(code, p.id);
  });
  return map;
});

const permCodeById = computed(() => {
  const map = new Map();
  (allPermissions.value || []).forEach(p => {
    map.set(p.id, normalizePermCode(p.code));
  });
  return map;
});

const indicatorStyle = computed(() => {
  return {
    width: `${indicatorWidth.value}px`,
    transform: `translate3d(${indicatorLeft.value}px, 0, 0)`,
  };
});

const tabSwitcherRef = ref(null);
const tabRoleRef = ref(null);
const tabPermissionRef = ref(null);
const tabDistributionRef = ref(null);
const indicatorLeft = ref(0);
const indicatorWidth = ref(0);
let tabResizeObserver;

// 分组显示权限（角色详情页）
const filteredPermissionGroups = computed(() => {
  const groups = {};
  const filter = permFilterText.value.toLowerCase();
  
  allPermissions.value.forEach(p => {
    if (filter && !p.name.toLowerCase().includes(filter) && !p.code.toLowerCase().includes(filter)) {
      return;
    }
    
    const groupName = getPermGroupName(p.code);
    
    if (!groups[groupName]) {
      groups[groupName] = { items: [], allChecked: false, isIndeterminate: false };
    }
    groups[groupName].items.push({ ...p, _depth: getPermDepth(p.code) });
  });

  // Update check status for each group
  for (const name in groups) {
    const group = groups[name];
    group.items.sort((a, b) => {
      const ma = getPermModuleKey(a.code);
      const mb = getPermModuleKey(b.code);
      if (ma !== mb) return ma.localeCompare(mb);
      const aa = getPermActionKey(a.code);
      const ab = getPermActionKey(b.code);
      if (aa.priority !== ab.priority) return aa.priority - ab.priority;
      return String(a.code || '').localeCompare(String(b.code || ''));
    });
    const checkedCount = group.items.filter(item => currentRolePermIds.value.includes(item.id)).length;
    group.allChecked = checkedCount === group.items.length && group.items.length > 0;
    group.isIndeterminate = checkedCount > 0 && checkedCount < group.items.length;
  }
  
  return groups;
});

const filteredPermGroups = computed(() => {
  const kw = permListFilter.value.toLowerCase();
  const list = (permissionDirectory.value || []).filter(p => {
    if (!kw) return true;
    return String(p.name || '').toLowerCase().includes(kw) || String(p.code || '').toLowerCase().includes(kw);
  });

  const groups = {};
  list.forEach(p => {
    const groupName = getPermGroupName(p.code);
    if (!groups[groupName]) groups[groupName] = { items: [] };
    groups[groupName].items.push({ ...p, _depth: getPermDepth(p.code) });
  });

  for (const name in groups) {
    groups[name].items.sort((a, b) => {
      const ma = getPermModuleKey(a.code);
      const mb = getPermModuleKey(b.code);
      if (ma !== mb) return ma.localeCompare(mb);
      const aa = getPermActionKey(a.code);
      const ab = getPermActionKey(b.code);
      if (aa.priority !== ab.priority) return aa.priority - ab.priority;
      return String(a.code || '').localeCompare(String(b.code || ''));
    });
  }

  return groups;
});

// --- Lifecycle ---
onMounted(() => {
  handleResize();
  window.addEventListener('resize', handleResize);
  const token = Cookies.get('token');
  if (token) {
    try {
      const decoded = jwtDecode(token);
      if (decoded && decoded.id !== undefined && decoded.id !== null) {
        currentUserId.value = Number(decoded.id);
      }
    } catch {}
  }
  if (route.query.tab) {
    activeTab.value = route.query.tab;
  }
  fetchRoles();
  fetchPermissions();
  fetchDisabledPermissions();
  fetchPermissionDirectory();
  updateIndicator();

  if (tabSwitcherRef.value && typeof ResizeObserver !== 'undefined') {
    tabResizeObserver = new ResizeObserver(() => updateIndicator());
    tabResizeObserver.observe(tabSwitcherRef.value);
  }
});

watch(activeTab, (val) => {
  router.replace({ query: { ...route.query, tab: val } });
  updateIndicator();
  if (val === 'distribution' && roleUsersData.value.length === 0) {
    // Deprecated
  }
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize);
  if (tabResizeObserver) tabResizeObserver.disconnect();
});

// 监听表单变化标记未保存（简单实现）
watch(
    () => [currentRoleForm, currentRolePermIds.value], 
    () => { 
        if(currentRole.value) hasChanges.value = true 
    }, 
    { deep: true }
);
// 重置 hasChanges 当切换角色时
watch(currentRole, () => { hasChanges.value = false });


// --- Methods: Common ---
const updateIndicator = async () => {
  await nextTick();
  const container = tabSwitcherRef.value;
  if (!container) return;

  const activeEl = activeTab.value === 'role'
    ? tabRoleRef.value
    : activeTab.value === 'permission'
      ? tabPermissionRef.value
      : tabDistributionRef.value;

  if (!activeEl) return;
  indicatorLeft.value = activeEl.offsetLeft;
  indicatorWidth.value = activeEl.offsetWidth;
};

const fetchRoles = async () => {
  roleLoading.value = true;
  try {
    const res = await axios.get('/api/v1/rbac/roles');
    if (res.data.code === 200) {
      roleTableData.value = res.data.data || [];
      if (!currentRole.value && roleTableData.value.length > 0) {
        const defaultRole = roleTableData.value.find(r => r.is_default) || roleTableData.value[0];
        if (defaultRole) await handleSelectRole(defaultRole);
      }
    }
  } catch(e) { console.error(e) } 
  finally { roleLoading.value = false; }
};

const fetchRoleUsers = async () => {
  roleUsersLoading.value = true;
  try {
    const res = await axios.get('/api/v1/rbac/roles/with_users');
    if (res.data.code === 200) {
      roleUsersData.value = res.data.data || [];
    } else {
      ElMessage.error(res.data.message || '获取人员分布失败');
    }
  } catch (e) {
    ElMessage.error('获取人员分布失败');
  } finally {
    roleUsersLoading.value = false;
  }
};

const fetchPermissions = async () => {
  permissionLoading.value = true;
  try {
    const res = await axios.get('/api/v1/rbac/permissions');
    if (res.data.code === 200) {
      allPermissions.value = res.data.data || [];
    }
  } catch(e) { console.error(e) }
  finally { permissionLoading.value = false; }
};

const fetchDisabledPermissions = async () => {
  try {
    const res = await axios.get('/api/v1/rbac/permissions/disabled');
    if (res.data.code === 200) {
      const codes = res.data.data?.codes || [];
      disabledPermCodes.value = codes.map(c => String(c || '').trim()).filter(Boolean);
    }
  } catch (e) {
    console.error(e);
  }
};

const fetchPermissionDirectory = async () => {
  permissionLoading.value = true;
  try {
    const res = await axios.get('/api/v1/rbac/permissions/directory');
    if (res.data.code === 200) {
      permissionDirectory.value = res.data.data || [];
    } else {
      ElMessage.error(res.data.message || '获取权限目录失败');
    }
  } catch (e) {
    ElMessage.error('获取权限目录失败');
  } finally {
    permissionLoading.value = false;
  }
};

const isGloballyDisabled = (code) => {
  const c = String(code || '').trim();
  if (!c) return false;
  return disabledPermCodes.value.includes(c);
};

const setDisabledCodes = (codes) => {
  disabledPermCodes.value = (codes || [])
    .map(c => String(c || '').trim())
    .filter(Boolean);
};

const updateDisabledOnServer = async (codes, loadingCode = '') => {
  disabledSavingCode.value = loadingCode;
  try {
    const payload = {
      codes: (codes || []).map(c => String(c || '').trim()).filter(Boolean),
    };
    const res = await axios.put('/api/v1/rbac/permissions/disabled', payload);
    if (res.data.code === 200) {
      setDisabledCodes(res.data.data?.codes || []);
      ElMessage.success(res.data.message || '保存成功');
    } else {
      ElMessage.error(res.data.message || '保存失败');
    }
  } catch (e) {
    ElMessage.error('保存失败');
  } finally {
    disabledSavingCode.value = '';
  }
};

const toggleGlobalDisabledForPerm = async (code) => {
  const c = String(code || '').trim();
  if (!c) return;
  const set = new Set(disabledPermCodes.value || []);
  if (set.has(c)) set.delete(c);
  else set.add(c);
  await updateDisabledOnServer(Array.from(set), c);
};

const setGlobalDisabledForPerm = async (code, disabled) => {
  const c = String(code || '').trim();
  if (!c) return;
  const set = new Set(disabledPermCodes.value || []);
  if (disabled) set.add(c);
  else set.delete(c);
  await updateDisabledOnServer(Array.from(set), c);
};

const handleSyncPermissions = async () => {
  permSyncing.value = true;
  try {
    const res = await axios.post('/api/v1/rbac/permissions/sync');
    if (res.data.code === 200) {
      ElMessage.success(res.data.message || '同步成功');
      const directory = res.data.data?.directory;
      if (Array.isArray(directory)) {
        permissionDirectory.value = directory;
      } else {
        await fetchPermissionDirectory();
      }
      await fetchPermissions();
    } else {
      ElMessage.error(res.data.message || '同步失败');
    }
  } catch (e) {
    ElMessage.error('同步失败');
  } finally {
    permSyncing.value = false;
  }
};

// --- Methods: Role Management ---

const handleSelectRole = async (role) => {
  // 如果是未保存的新建角色，提示放弃
  if (currentRole.value?.id === 'new' && hasChanges.value) {
     try {
       await ElMessageBox.confirm('当前新建角色未保存，切换将丢失数据，是否继续？', '警告', { type: 'warning' });
     } catch { return; }
  }

  currentRole.value = role;
  // 填充表单
  Object.assign(currentRoleForm, {
    name: role.name,
    code: role.code,
    description: role.description
  });
  
  // 获取该角色的权限
  currentRolePermIds.value = [];
  try {
    const res = await axios.get(`/api/v1/rbac/roles/${role.id}/permissions`);
    if (res.data.code === 200) {
      currentRolePermIds.value = (res.data.data || []).map(p => p.id);
    }
  } catch (e) { console.error(e); }

  roleMembersPage.value = 1;
  await fetchRoleMembers(role.id);
  
  hasChanges.value = false;
};

const handleCreateRole = () => {
  const newRole = { id: 'new', name: '新角色', code: '', description: '' };
  roleTableData.value.unshift(newRole);
  currentRole.value = newRole;
  Object.assign(currentRoleForm, newRole);
  currentRolePermIds.value = [];
  hasChanges.value = true;
};

const saveCurrentRole = async () => {
  if (!currentRoleForm.name || !currentRoleForm.code) {
    ElMessage.warning('角色名称和编码不能为空');
    return;
  }
  
  roleSaving.value = true;
  try {
    let roleId = currentRole.value.id;
    // 1. 保存/更新角色基本信息
    if (roleId === 'new') {
      const res = await axios.post('/api/v1/rbac/roles', currentRoleForm);
      if (res.data.code !== 200) throw new Error(res.data.message);
      roleId = res.data.data.id; // 获取新ID
      ElMessage.success('角色创建成功');
    } else {
      const res = await axios.put(`/api/v1/rbac/roles/${roleId}`, currentRoleForm);
      if (res.data.code !== 200) throw new Error(res.data.message);
      ElMessage.success('角色更新成功');
    }
    
    // 2. 保存权限关联
    const permRes = await axios.put(`/api/v1/rbac/roles/${roleId}/permissions`, {
      permission_ids: currentRolePermIds.value
    });
    
    // 刷新列表
    await fetchRoles();
    // 重新选中该角色
    const updatedRole = roleTableData.value.find(r => r.id === roleId);
    if(updatedRole) handleSelectRole(updatedRole);
    
    try {
      const refreshRes = await axios.post('/api/v1/auth/refresh');
      const nextToken = refreshRes?.data?.token;
      if (nextToken) {
        Cookies.set('token', nextToken, { sameSite: 'lax' });
      }
    } catch {}
    await router.replace({ query: { ...route.query, __perm_refresh: String(Date.now()) } });

    hasChanges.value = false;
  } catch (e) {
    ElMessage.error(e.message || '保存失败');
  } finally {
    roleSaving.value = false;
  }
};

const handleRoleCommand = async (cmd, role) => {
  if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确定删除角色 ${role.name} 吗？`, '警告', { type: 'warning' });
      const res = await axios.delete(`/api/v1/rbac/roles/${role.id}`);
      if (res.data.code === 200) {
        ElMessage.success('删除成功');
        if (currentRole.value?.id === role.id) currentRole.value = null;
        fetchRoles();
      }
    } catch {}
  } else if (cmd === 'default') {
      await handleSetDefaultRole(role);
  } else if (cmd === 'copy') {
      ElMessage.info('复制功能开发中...');
  }
};

const handleSetDefaultRole = async (role) => {
  if (!role || role.id === 'new') return;
  try {
    await ElMessageBox.confirm(`确定将「${role.name}」设为默认角色吗？`, '提示', { type: 'warning' });
    const res = await axios.post(`/api/v1/rbac/roles/${role.id}/default`);
    if (res.data.code === 200) {
      ElMessage.success(res.data.message || '设置成功');
      roleTableData.value = roleTableData.value.map(r => ({ ...r, is_default: r.id === role.id }));
      if (currentRole.value?.id === role.id) {
        currentRole.value = { ...currentRole.value, is_default: true };
      }
    } else {
      ElMessage.error(res.data.message || '设置失败');
    }
  } catch {}
};

const fetchRoleMembers = async (roleId) => {
  if (!roleId || roleId === 'new') {
    roleMembers.value = [];
    roleMembersTotal.value = 0;
    return;
  }
  roleMembersLoading.value = true;
  try {
    const res = await axios.get(`/api/v1/rbac/roles/${roleId}/users`, {
      params: { page: roleMembersPage.value, page_size: roleMembersPageSize.value }
    });
    if (res.data.code === 200) {
      roleMembers.value = res.data.data || [];
      roleMembersTotal.value = Number(res.data?.meta?.total ?? roleMembers.value.length ?? 0);
    } else {
      ElMessage.error(res.data.message || '获取成员失败');
    }
  } catch (e) {
    ElMessage.error('获取成员失败');
  } finally {
    roleMembersLoading.value = false;
  }
};

const handleRoleMembersPageChange = async (page) => {
  roleMembersPage.value = Number(page || 1);
  if (currentRole.value?.id && currentRole.value.id !== 'new') {
    await fetchRoleMembers(currentRole.value.id);
  }
};

const handleRoleMembersPageSizeChange = async (size) => {
  roleMembersPageSize.value = Number(size || 20);
  roleMembersPage.value = 1;
  if (currentRole.value?.id && currentRole.value.id !== 'new') {
    await fetchRoleMembers(currentRole.value.id);
  }
};

const fetchAvailableUsers = async ({ q } = {}) => {
  if (!currentRole.value?.id || currentRole.value.id === 'new') return;
  availableUsersLoading.value = true;
  try {
    const res = await axios.get(`/api/v1/rbac/roles/${currentRole.value.id}/available_users`, {
      params: { q: String(q ?? availableUsersQuery.value ?? ''), page: 1, page_size: 50 }
    });
    if (res.data.code === 200) {
      availableUsers.value = res.data.data || [];
    } else {
      ElMessage.error(res.data.message || '获取可选用户失败');
    }
  } catch (e) {
    ElMessage.error('获取可选用户失败');
  } finally {
    availableUsersLoading.value = false;
  }
};

const handleAvailableUsersRemoteSearch = async (query) => {
  availableUsersQuery.value = String(query ?? '');
  await fetchAvailableUsers({ q: availableUsersQuery.value });
};

const openAddMembersDialog = async () => {
  if (!currentRole.value || currentRole.value.id === 'new') return;
  addMembersDialogVisible.value = true;
  selectedUserIds.value = [];
  availableUsersQuery.value = '';
  await fetchAvailableUsers({ q: '' });
};

const handleAddMembers = async () => {
  if (!currentRole.value || currentRole.value.id === 'new') return;
  if (!selectedUserIds.value.length) {
    ElMessage.warning('请选择要添加的用户');
    return;
  }
  roleMembersLoading.value = true;
  try {
    const res = await axios.post(`/api/v1/rbac/roles/${currentRole.value.id}/users`, { user_ids: selectedUserIds.value });
    if (res.data.code === 200) {
      ElMessage.success(res.data.message || '添加成功');
      addMembersDialogVisible.value = false;
      roleMembersPage.value = 1;
      await fetchRoleMembers(currentRole.value.id);
    } else {
      ElMessage.error(res.data.message || '添加失败');
    }
  } catch (e) {
    ElMessage.error('添加失败');
  } finally {
    roleMembersLoading.value = false;
  }
};

const handleRemoveMember = async (user) => {
  if (!currentRole.value || currentRole.value.id === 'new') return;
  try {
    await ElMessageBox.confirm(`确定将用户「${user.username}」从该角色移除吗？`, '提示', { type: 'warning' });
    const res = await axios.delete(`/api/v1/rbac/roles/${currentRole.value.id}/users/${user.id}`);
    if (res.data.code === 200) {
      ElMessage.success(res.data.message || '移除成功');
      if (roleMembers.value.length <= 1 && roleMembersPage.value > 1) {
        roleMembersPage.value -= 1;
      }
      await fetchRoleMembers(currentRole.value.id);
    } else {
      ElMessage.error(res.data.message || '移除失败');
    }
  } catch {}
};

const togglePerm = (id) => {
  const code = permCodeById.value.get(id);
  if (code && isGloballyDisabled(code)) {
    return;
  }
  if (!code) {
    const index = currentRolePermIds.value.indexOf(id);
    if (index > -1) currentRolePermIds.value.splice(index, 1);
    else currentRolePermIds.value.push(id);
    return;
  }

  const selectedCodes = currentRolePermIds.value
    .map(pid => permCodeById.value.get(pid))
    .filter(Boolean);

  const isEnabled = currentRolePermIds.value.includes(id);
  let nextCodes;
  if (isEnabled) {
    nextCodes = buildStableSelectionAfterRemoval(selectedCodes.filter(c => c !== code));
  } else {
    nextCodes = expandPermCodes([...selectedCodes, code]);
  }

  const nextIds = nextCodes
    .map(c => permIdByCode.value.get(c))
    .filter(Boolean);
  currentRolePermIds.value = Array.from(new Set(nextIds));
};

const handleGroupCheckAll = (val, group) => {
  const ids = group.items.map(i => i.id);
  if (val) {
    const codes = ids.map(id => permCodeById.value.get(id)).filter(Boolean);
    const expanded = expandPermCodes(codes);
    const nextIds = expanded.map(c => permIdByCode.value.get(c)).filter(Boolean);
    currentRolePermIds.value = Array.from(new Set([...currentRolePermIds.value, ...nextIds]));
  } else {
    currentRolePermIds.value = currentRolePermIds.value.filter(id => !ids.includes(id));
  }
};

// --- Methods: Permission Management ---

const handleSelectPerm = (perm) => {
    currentPerm.value = perm;
    Object.assign(currentPermForm, perm);
};

const handleCreatePerm = () => {
    const newPerm = { id: 'new', name: '新权限', code: '', description: '' };
    // 临时添加到列表以便选中，保存后刷新
    // allPermissions.value.unshift(newPerm); 
    currentPerm.value = newPerm;
    Object.assign(currentPermForm, newPerm);
};

const saveCurrentPerm = async () => {
    if (!currentPerm.value?.id) {
        ElMessage.warning('该权限未同步入库，无法保存');
        return;
    }
    if (!currentPermForm.name || !currentPermForm.code) {
        ElMessage.warning('名称和编码不能为空');
        return;
    }
    permSaving.value = true;
    try {
        const payload = {
            name: currentPermForm.name,
            code: currentPermForm.code,
            description: currentPermForm.description
        };
        if (currentPerm.value.id === 'new') {
            const res = await axios.post('/api/v1/rbac/permissions', payload);
            if (res.data.code === 200) {
                ElMessage.success('创建成功');
                await fetchPermissions();
                await fetchPermissionDirectory();
                currentPerm.value = null;
            } else { throw new Error(res.data.message); }
        } else {
            const res = await axios.put(`/api/v1/rbac/permissions/${currentPerm.value.id}`, payload);
            if (res.data.code === 200) {
                ElMessage.success('更新成功');
                await fetchPermissions();
                await fetchPermissionDirectory();
            } else { throw new Error(res.data.message); }
        }
    } catch(e) {
        ElMessage.error(e.message || '保存失败');
    } finally {
        permSaving.value = false;
    }
};

const handlePermDelete = async (perm) => {
    try {
        if (perm.in_directory) {
            ElMessage.warning('系统权限不允许删除');
            return;
        }
        await ElMessageBox.confirm(`确定删除权限 ${perm.name} 吗？`, '提示', { type: 'warning' });
        const res = await axios.delete(`/api/v1/rbac/permissions/${perm.id}`);
        if (res.data.code === 200) {
            ElMessage.success('删除成功');
            if (currentPerm.value?.id === perm.id) currentPerm.value = null;
            await fetchPermissions();
            await fetchPermissionDirectory();
        }
    } catch {}
};

</script>

<style scoped>
/* 定义通用/浅色主题变量 */
.rbac-container {
  --bg-dark: #f5f7fa; /* 整体背景 */
  --bg-card: #ffffff; /* 卡片/面板背景 */
  --bg-hover: #f0f2f5; /* 悬停背景 */
  --bg-active: #ecf5ff; /* 激活状态背景 */
  --primary-color: #409eff; /* 主色调 */
  --text-primary: #303133; /* 主文本 */
  --text-secondary: #909399; /* 次级文本 */
  --border-color: #dcdfe6; /* 边框颜色 */
  
  height: 100%;
  display: flex;
  flex-direction: column;
  background-color: var(--bg-dark);
  color: var(--text-primary);
  border-radius: 8px;
  overflow: hidden;
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

/* Header */
.rbac-header {
  height: 60px;
  background-color: var(--bg-card);
  border-bottom: 1px solid var(--border-color);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
}

.page-title {
  font-size: 18px;
  font-weight: 600;
  display: flex;
  align-items: center;
  color: var(--text-primary);
}

.info-icon {
  margin-left: 8px;
  color: var(--text-secondary);
  cursor: help;
  font-size: 16px;
}

.tab-switcher {
  position: relative;
  display: flex;
  width: 360px;
  max-width: 100%;
  background-color: var(--bg-hover);
  border-radius: 20px;
  padding: 4px;
}

.tab-item {
  flex: 1;
  padding: 6px 20px;
  cursor: pointer;
  border-radius: 16px;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-secondary);
  transition: all 0.3s;
  z-index: 1;
}

.tab-item.active {
  color: #fff;
  font-weight: 500;
}

.tab-indicator {
  position: absolute;
  top: 4px;
  bottom: 4px;
  left: 0;
  background-color: var(--primary-color);
  border-radius: 16px;
  transition: transform 0.22s cubic-bezier(0.22, 1, 0.36, 1), width 0.22s cubic-bezier(0.22, 1, 0.36, 1);
  will-change: transform, width;
  z-index: 0;
  box-shadow: 0 2px 4px rgba(64, 158, 255, 0.3);
}

.distribution-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px;
  overflow: auto;
}

.distribution-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.distribution-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}

.role-cards {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: 12px;
}

.role-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.role-card-name {
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.role-user-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.user-tag {
  max-width: 100%;
}

/* Content */
.rbac-content {
  flex: 1;
  overflow: hidden;
  position: relative;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.view-container {
  display: flex;
  flex: 1;
  min-height: 0;
  width: 100%;
}

/* Panels */
.left-panel {
  width: 320px;
  background-color: var(--bg-card);
  border-right: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  min-height: 0;
}

.right-panel {
  flex: 1;
  background-color: #ffffff; /* 确保右侧也是白色或根据需要微调 */
  display: flex;
  flex-direction: column;
  min-width: 0; /* 防止内容撑开 */
  min-height: 0;
}

.panel-header {
  height: 50px;
  padding: 0 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--bg-card);
}

.panel-title {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
}

/* Role List */
.role-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.role-item {
  display: flex;
  align-items: center;
  padding: 12px;
  margin-bottom: 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  background-color: transparent;
  border: 1px solid transparent;
}

.role-item:hover {
  background-color: var(--bg-hover);
}

.role-item.active {
  background-color: var(--bg-active);
  border-color: #c6e2ff;
  border-left: 3px solid var(--primary-color);
}

.role-icon {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background-color: var(--bg-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-right: 12px;
  color: var(--primary-color);
}

.role-info {
  flex: 1;
  min-width: 0;
}

.role-name {
  font-size: 14px;
  font-weight: 500;
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--text-primary);
}

.role-meta {
  font-size: 12px;
  color: var(--text-secondary);
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.role-actions {
  opacity: 0;
  transition: opacity 0.2s;
}

.role-item:hover .role-actions {
  opacity: 1;
}

.action-icon {
  cursor: pointer;
  padding: 4px;
  color: var(--text-secondary);
}

.action-icon:hover {
  color: var(--primary-color);
}

/* Right Panel Body */
.panel-body {
  flex: 1;
  overflow-y: auto;
  min-height: 0;
  padding: 20px;
  background-color: #fcfcfc;
}

.config-section {
  background-color: var(--bg-card);
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
  border: 1px solid #ebeef5;
  box-shadow: 0 1px 4px rgba(0,0,0,0.02);
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-left: 4px solid var(--primary-color);
  padding-left: 10px;
  color: var(--text-primary);
}

.pagination-container {
  margin-top: 12px;
  display: flex;
  justify-content: flex-end;
}

/* Permission Matrix */
.perm-matrix {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 16px;
}

.perm-group-card {
  background-color: #fff;
  border-radius: 6px;
  overflow: hidden;
  border: 1px solid #ebeef5;
  transition: box-shadow 0.2s;
}

.perm-group-card:hover {
  box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
}

.group-header {
  padding: 10px 12px;
  background-color: #f5f7fa;
  display: flex;
  justify-content: space-between;
  align-items: center;
  border-bottom: 1px solid #ebeef5;
}

.group-name {
  font-weight: 600;
  font-size: 13px;
  color: var(--text-primary);
}

.group-items {
  padding: 8px;
}

.perm-item {
  display: flex;
  align-items: center;
  padding: 8px;
  border-radius: 4px;
  cursor: pointer;
  transition: background 0.2s;
}

.perm-item.child {
  padding-left: 18px;
}

.perm-item.grandchild {
  padding-left: 28px;
}

.perm-item:hover {
  background-color: var(--bg-hover);
}

.perm-item.active {
  /* background-color: rgba(64, 158, 255, 0.1); */
}

.perm-switch {
  margin-right: 12px;
}

.perm-label .name {
  font-size: 13px;
  line-height: 1.2;
  color: var(--text-primary);
}

.perm-label .code {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 2px;
}

/* Permission View Styles */
.search-bar {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-color);
  background-color: var(--bg-card);
}

.perm-tree-list {
  flex: 1;
  overflow-y: auto;
  background-color: var(--bg-card);
}

.perm-tree-group-header {
  padding: 10px 16px;
  font-weight: 600;
  font-size: 12px;
  color: var(--text-secondary);
  background-color: var(--bg-dark);
  border-bottom: 1px solid var(--border-color);
}

.perm-tree-item {
  display: flex;
  align-items: center;
  padding: 12px 16px;
  cursor: pointer;
  border-bottom: 1px solid #ebeef5;
}

.perm-tree-item.child {
  padding-left: 28px;
}

.perm-tree-item.grandchild {
  padding-left: 40px;
}

.perm-tree-item:hover {
  background-color: var(--bg-hover);
}

.perm-tree-item.active {
  background-color: var(--bg-active);
  border-right: 3px solid var(--primary-color);
}

.item-icon {
  margin-right: 12px;
  color: var(--text-secondary);
}

.item-content {
  flex: 1;
  min-width: 0;
}

.item-title {
  font-size: 14px;
  color: var(--text-primary);
}

.item-subtitle {
  font-size: 12px;
  color: var(--text-secondary);
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.perm-tree-item:hover .delete-btn,
.perm-tree-item:hover .global-disable-btn {
  opacity: 1;
}

/* Scrollbar */
.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}
.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}
.custom-scrollbar::-webkit-scrollbar-thumb {
  background: #c0c4cc;
  border-radius: 3px;
}
.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: #909399;
}

/* Transitions */
.fade-slide-enter-active,
.fade-slide-leave-active {
  transition: all 0.3s ease;
}

.fade-slide-enter-from {
  opacity: 0;
  transform: translateX(10px);
}

.fade-slide-leave-to {
  opacity: 0;
  transform: translateX(-10px);
}

/* Empty State */
.empty-state {
  justify-content: center;
  align-items: center;
  background-color: #fcfcfc;
}

/* Distribution View */
.dist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
}

.dist-card {
  background: #fff;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0,0,0,0.04);
  overflow: hidden;
  border: 1px solid #ebeef5;
  transition: transform 0.2s;
  display: flex;
  flex-direction: column;
  height: 200px;
}

.dist-card:hover {
  transform: translateY(-2px);
  box-shadow: 0 4px 16px rgba(0,0,0,0.08);
}

.dist-header {
  padding: 16px;
  background: #f8f9fb;
  border-bottom: 1px solid #f0f2f5;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.d-title {
  display: flex;
  flex-direction: column;
}

.d-name {
  font-weight: 600;
  font-size: 15px;
  color: var(--text-primary);
}

.d-code {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 2px;
}

.dist-body {
  flex: 1;
  padding: 16px;
  overflow-y: auto;
}

.user-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.u-tag {
  background-color: #f0f9eb;
  border-color: #e1f3d8;
  color: #67c23a;
}

.empty-users {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 13px;
  background: repeating-linear-gradient(
    45deg,
    #fcfcfc,
    #fcfcfc 10px,
    #f8f9fa 10px,
    #f8f9fa 20px
  );
}

@media (max-width: 768px) {
  .rbac-container {
    height: auto;
    min-height: 100%;
    border-radius: 0;
  }
  
  .rbac-header {
    height: auto;
    flex-direction: column;
    align-items: stretch;
    padding: 16px;
    gap: 12px;
  }
  
  .page-title {
    justify-content: flex-start;
  }
  
  .tab-switcher {
    width: 100%;
  }
  
  .view-container {
    flex-direction: column;
  }
  
  .left-panel {
    width: 100%;
    border-right: none;
    height: 100%;
  }
  
  .right-panel {
    width: 100%;
    height: 100%;
  }
  
  .perm-matrix {
    grid-template-columns: 1fr;
  }
  
  .config-section {
    padding: 12px;
  }
  
  .role-cards {
    grid-template-columns: 1fr;
  }
  
  .role-actions, .delete-btn {
    opacity: 1;
  }
  
  .panel-body {
    padding: 12px;
  }

  /* Adjust dialog for mobile if needed globally, but here we used inline style for width */
  :deep(.el-dialog) {
      margin-top: 5vh !important;
  }
}
</style>
