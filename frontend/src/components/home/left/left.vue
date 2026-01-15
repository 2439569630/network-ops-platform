<template>
    <div class="leftbox">
        <el-row class="tac" :style="{ height: '100%' }">
            <el-col :span="24" class="tac">
                <el-menu 
                    active-text-color="#ffd04b" 
                    background-color="transparent" 
                    class="el-menu-vertical-demo" 
                    :default-active="activeMenu"
                    text-color="#fff"
                    :unique-opened="true"
                >
                    <!-- 1. 系统概览 (所有人可见) -->
                    <el-menu-item index="dashboard" @click="goto('/user/dashboard')" v-if="hasPerm('sys:dashboard:view')">
                        <el-icon><Odometer /></el-icon>
                        <span>系统概览</span>
                    </el-menu-item>

                    <el-menu-item index="message" @click="goto('/user/message')">
                         <el-icon><Message /></el-icon>
                         <el-badge :is-dot="msgStore.siteMessageUnreadCount > 0" class="menu-badge-text">
                            <span>消息中心</span>
                         </el-badge>
                    </el-menu-item>

                    <!-- 2. 个人中心 (所有人可见) -->
                    <el-menu-item index="profile" @click="goto('/user/home')">
                         <el-icon><UserFilled /></el-icon>
                         <span>个人中心</span>
                    </el-menu-item>

                    <!-- 3. 业务管理 (设备与位置) -->
                    <el-sub-menu index="business" v-if="hasAnyPerm(['sys:device:list', 'sys:location:manage'])">
                         <template #title>
                            <el-icon><OfficeBuilding /></el-icon>
                            <span>业务管理</span>
                        </template>
                        <el-menu-item index="location" @click="goto('/user/location')" v-if="hasPerm('sys:location:manage')">
                            <el-icon><Location /></el-icon>
                            <span>位置管理</span>
                        </el-menu-item>
                        <el-menu-item index="device" @click="goto('/user/device')" v-if="hasPerm('sys:device:list')">
                            <el-icon><Monitor /></el-icon>
                            <span>设备管理</span>
                        </el-menu-item>
                    </el-sub-menu>
                    
                    <!-- 4. 运维工单 (所有人可见) -->
                    <el-sub-menu index="repair" v-if="hasAnyPerm(['sys:repair:create', 'sys:repair:view', 'sys:repair:handle', 'sys:repair:manage'])">
                        <template #title>
                            <el-icon><Memo /></el-icon>
                            <span>运维工单</span>
                        </template>
                        <el-menu-item index="repair-apply" @click="goto('/user/repair/apply')" v-if="hasAnyPerm(['sys:repair:create', 'sys:repair:manage'])">
                            <el-icon><EditPen /></el-icon>
                            <span>我要报修</span>
                        </el-menu-item>
                        <el-menu-item index="repair-list" @click="goto('/user/repair/list')" v-if="hasAnyPerm(['sys:repair:view', 'sys:repair:handle', 'sys:repair:manage'])">
                            <el-icon><List /></el-icon>
                            <span>工单列表</span>
                        </el-menu-item>
                    </el-sub-menu>

                    <!-- 5. 系统管理 (仅管理员) -->
                    <el-sub-menu index="system" v-if="hasAnyPerm(['sys:user:view', 'sys:user:import', 'sys:config:view'])">
                        <template #title>
                            <el-icon><Setting /></el-icon>
                            <span>系统管理</span>
                        </template>
                        <el-menu-item index="role" @click="goto('/user/role')" v-if="isSuper">
                            <el-icon><Avatar /></el-icon>
                            <span>角色与权限管理</span>
                        </el-menu-item>
                        <el-menu-item index="user-import" @click="goto('/user/user-import')" v-if="hasPerm('sys:user:import')">
                            <el-icon><User /></el-icon>
                            <span>批量导入用户</span>
                        </el-menu-item>
                         <el-menu-item index="config" @click="goto('/user/config')" v-if="hasPerm('sys:config:view')">
                            <el-icon><Tools /></el-icon>
                            <span>全局配置</span>
                        </el-menu-item>
                    </el-sub-menu>
                    
                    <el-menu-item index="logout" @click="goto('/Login')">
                        <el-icon><SwitchButton /></el-icon>
                        <span>退出登录</span>
                    </el-menu-item>

                </el-menu>
            </el-col>
        </el-row>
    </div>
</template>

<script setup>
import { useRouter, useRoute } from 'vue-router';
import { onMounted, onBeforeUnmount, computed, watch } from 'vue';
import Cookies from 'js-cookie';
import axios from '@/axios/axios';
import { homeDataStore } from '@/components/home/home/data';
import { messageCenterDataStore } from '@/components/MessageCenter/date';
import { 
    UserFilled, Monitor, Connection, Message, Setting, SwitchButton, Odometer, 
    OfficeBuilding, Location, User, DataLine, School, Avatar, Tools,
    Memo, EditPen, List
} from '@element-plus/icons-vue';

const router = useRouter();
const route = useRoute();
const store = homeDataStore();
const msgStore = messageCenterDataStore();
const isSuper = computed(() => Boolean(store.isSuper));
const permissions = computed(() => (Array.isArray(store.permissions) ? store.permissions : []));

const activeMenu = computed(() => {
    const path = route.path;
    if (path.includes('/user/dashboard')) return 'dashboard';
    
    // 个人中心
    if (path.includes('/user/home')) return 'profile';
    if (path.includes('/user/message')) return 'message';

    // 业务管理
    if (path.includes('/user/location')) return 'location';
    if (path.includes('/user/device')) {
        // 特殊处理：device路由被多个菜单共用
        // 如果是从SNMP入口进来的，理论上应该区分，但目前路由相同
        // 建议未来拆分路由。暂时默认高亮设备管理
        return 'device'; 
    }

    // 监控运维 (暂时只有SNMP，且路由复用了device)
    // if (path.includes('/user/monitor')) return 'snmp';

    // 运维工单
    if (path.includes('/user/repair/apply')) return 'repair-apply';
    if (path.includes('/user/repair/list') || path.includes('/user/repair/detail')) return 'repair-list';

    // 系统管理
    if (path.includes('/user/organization')) return 'organization';
    if (path.includes('/user/role')) return 'role';
    if (path.includes('/user/permission')) return 'role';
    if (path.includes('/user/user-import')) return 'user-import';
    if (path.includes('/user/config')) return 'config';

    return 'dashboard';
});

const hasPerm = (perm) => {
    // 超级管理员拥有所有权限
    if (isSuper.value) return true;
    return permissions.value.includes(perm);
};

// 工具方法：判断是否有数组中任意一个权限
const hasAnyPerm = (perms) => {
    if (isSuper.value) return true;
    return perms.some(p => permissions.value.includes(p));
}

let permTimer = null;
let authRefreshListener = null;

const syncAuthAndPerms = async (options = {}) => {
  const force = Boolean(options.force);
  store.syncAuthFromToken();
  if (!Cookies.get('token')) {
    return;
  }
  await store.fetchPermissions({ force });
};

onMounted(async () => {
  await syncAuthAndPerms();

  try {
    const res = await axios.post('/api/v1/auth/refresh');
    if (res.data && res.data.token) {
        await syncAuthAndPerms({ force: true });
    }
  } catch (e) {
    return;
  }

  authRefreshListener = async () => {
    await syncAuthAndPerms({ force: true });
  };
  window.addEventListener('auth:refreshed', authRefreshListener);

  permTimer = setInterval(() => {
    syncAuthAndPerms({ force: true });
  }, 30000);
});

onBeforeUnmount(() => {
  if (permTimer) {
    clearInterval(permTimer);
    permTimer = null;
  }
  if (authRefreshListener) {
    window.removeEventListener('auth:refreshed', authRefreshListener);
    authRefreshListener = null;
  }
});

watch(
  () => route.fullPath,
  () => {
    store.syncAuthFromToken();
  }
);

const goto = (path) => {
    if (String(path).toLowerCase() === '/login') {
        Cookies.remove('token');
    }
    router.push(path);
}
</script>

<style scoped>
.leftbox {
    width: 100%;
    height: 100%;
    color: white;
    padding: 10px;
    display: flex;
    background: linear-gradient(180deg, #1e3a8a 0%, #1e40af 100%);
    box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
}

.tac {
    display: block;
    width: 100%;
}
.el-col-24 {
    max-width: none;
    background: none;
}
.menu {
    background: none;
}

:deep(.el-menu) {
    border-right: none;
}

:deep(.menu-badge-text) {
    display: inline-flex;
    align-items: center;
}

:deep(.menu-badge-text .el-badge__content.is-dot) {
    top: 12px;
    right: -6px;
}
</style>
