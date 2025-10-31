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
    /* 新增以下属性 */
    display: flex;
    /* 设置为 Flex 布局 */
background: rgba(26, 54, 93, 0.8);

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
    /* background: rgba(45, 55, 72, 0.6); */
    color: #fff;
    border: 0;
}
.el-menu {
    border: 0;
    color: #fff;
    background: none;

}
.el-menu-item {
    color: #fff;
}
.el-menu-item:hover {
    background: rgba(116, 128, 147, 0.6);
}

</style>