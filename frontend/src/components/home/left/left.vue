<template>
    <div class="leftbox">
        <el-row class="tac" :style="{ height: '100%' }">
            <el-col :span="12" class="tac">
                <el-menu 
                    active-text-color="#ffd04b" 
                    background-color="transparent" 
                    class="el-menu-vertical-demo" 
                    :default-active="activeMenu"
                    text-color="#fff"
                    :unique-opened="true"
                >
                    <!-- 1. 系统概览 (所有人可见) -->
                    <el-menu-item index="dashboard" @click="goto('/user/dashboard')">
                        <el-icon><Odometer /></el-icon>
                        <span>系统概览</span>
                    </el-menu-item>

                    <!-- 2. 个人工作台 (所有人可见) -->
                    <el-sub-menu index="workspace">
                        <template #title>
                            <el-icon><User /></el-icon>
                            <span>个人工作台</span>
                        </template>
                        <el-menu-item index="profile" @click="goto('/user/home')">
                             <el-icon><UserFilled /></el-icon>
                             <span>个人中心</span>
                        </el-menu-item>
                        <el-menu-item index="message" @click="goto('/user/message')">
                             <el-icon><Message /></el-icon>
                             <span>消息中心</span>
                        </el-menu-item>
                    </el-sub-menu>

                    <!-- 3. 业务管理 (设备与位置) -->
                    <el-sub-menu index="business" v-if="hasAnyPerm(['sys:device:list', 'sys:location:view'])">
                         <template #title>
                            <el-icon><OfficeBuilding /></el-icon>
                            <span>业务管理</span>
                        </template>
                        <el-menu-item index="location" @click="goto('/user/location')" v-if="hasPerm('sys:device:list')">
                            <el-icon><Location /></el-icon>
                            <span>位置管理</span>
                        </el-menu-item>
                        <el-menu-item index="device" @click="goto('/user/device')" v-if="hasPerm('sys:device:list')">
                            <el-icon><Monitor /></el-icon>
                            <span>设备管理</span>
                        </el-menu-item>
                    </el-sub-menu>
                    
                    <!-- 4. 运维工单 (所有人可见) -->
                    <el-sub-menu index="repair">
                        <template #title>
                            <el-icon><Memo /></el-icon>
                            <span>运维工单</span>
                        </template>
                        <el-menu-item index="repair-apply" @click="goto('/user/repair/apply')">
                            <el-icon><EditPen /></el-icon>
                            <span>我要报修</span>
                        </el-menu-item>
                        <el-menu-item index="repair-list" @click="goto('/user/repair/list')">
                            <el-icon><List /></el-icon>
                            <span>工单列表</span>
                        </el-menu-item>
                    </el-sub-menu>

                    <!-- 5. 系统管理 (仅管理员) -->
                    <el-sub-menu index="system" v-if="hasAnyPerm(['sys:user:view', 'sys:config:view'])">
                        <template #title>
                            <el-icon><Setting /></el-icon>
                            <span>系统管理</span>
                        </template>
                        <el-menu-item index="role" @click="goto('/user/role')" v-if="hasPerm('sys:user:view')">
                            <el-icon><Avatar /></el-icon>
                            <span>角色与权限管理</span>
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
import { ref, onMounted, computed } from 'vue';
import { jwtDecode } from 'jwt-decode';
import Cookies from 'js-cookie';
import { 
    UserFilled, Monitor, Connection, Message, Setting, SwitchButton, Odometer, 
    OfficeBuilding, Location, User, DataLine, School, Avatar, Tools,
    Memo, EditPen, List
} from '@element-plus/icons-vue';

const router = useRouter();
const route = useRoute();
const userRole = ref(2); // 默认普通用户
const permissions = ref([]);

const activeMenu = computed(() => {
    const path = route.path;
    if (path.includes('/user/dashboard')) return 'dashboard';
    
    // 个人工作台
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
    if (path.includes('/user/config')) return 'config';

    return 'dashboard';
});

const hasPerm = (perm) => {
    // 超级管理员拥有所有权限
    if (userRole.value === 0) return true;
    return permissions.value.includes(perm);
};

// 工具方法：判断是否有数组中任意一个权限
const hasAnyPerm = (perms) => {
    if (userRole.value === 0) return true;
    return perms.some(p => permissions.value.includes(p));
}

onMounted(() => {
  const token = Cookies.get('token');
  if (token) {
    try {
        const decoded = jwtDecode(token);
        userRole.value = Number(decoded.permission_level);
        // 如果 token 中包含 permissions
        if (decoded.permissions) {
             permissions.value = decoded.permissions;
        } else {
             // 兼容旧 Token 或未包含的情况，按 Role 映射
             if (userRole.value === 1) {
                 // 运维人员权限
                 permissions.value = ["sys:device:list", "sys:monitor:view", "sys:location:view"];
             } else if (userRole.value === 2) {
                 // 普通用户权限（通常只有查看自己的信息）
                 permissions.value = [];
             }
        }
    } catch (e) {
        console.error("Token decode error", e);
    }
  }
});

const goto = (path) => {
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
.el-col-12 {
    max-width: none;
    background: none;
}
.menu {
    background: none;
}
</style>
