<template>
    <div class="leftbox">
        <el-row class="tac" :style="{ height: '100%' }">
            <el-col :span="12" class="tac">
                <el-menu default-active="0" @open="handleOpen" @close="handleClose">
                    <el-menu-item-group class="menu">
                        <el-menu-item index="1" @click="goto('/user/home')">首页</el-menu-item>
                        <el-menu-item index="2" @click="goto('/user/device')">设备管理</el-menu-item>
                        <el-menu-item index="3" @click="goto('/user/device')">SNMP</el-menu-item>
                        <el-menu-item index="4" @click="goto('/user/device')">消息推送</el-menu-item>
                        <el-menu-item index="5" @click="goto('/user/device')">全局配置</el-menu-item>
                        <el-menu-item index="10" @click="goto('/Login')">退出登录</el-menu-item>
                    </el-menu-item-group>
                </el-menu>
            </el-col>
        </el-row>
    </div>
</template>

<script setup>

import { useRouter } from 'vue-router';
import router from '@/router';

const handleOpen = (key, keyPath) => {
    console.log(key, keyPath);
};
const handleClose = (key, keyPath) => {
    console.log(key, keyPath);
};

const goto = (path) => {
    router.push(path);
};


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
    color: #fff;
    border: 0;
}
.el-menu {
    border: 0;
    color: #fff;
    background: none;
}
.el-menu-item {
    color: rgba(255, 255, 255, 0.9);
    border-radius: 8px;
    margin: 4px 0;
    transition: all 0.3s ease;
}
.el-menu-item:hover {
    background: rgba(255, 255, 255, 0.15);
    color: #fff;
    transform: translateX(4px);
}
.el-menu-item.is-active {
    background: rgba(255, 255, 255, 0.2);
    color: #fff;
    font-weight: 500;
}
.el-menu-item-group {
    padding: 8px 0;
}

</style>