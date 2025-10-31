<template>
    <div class="device-list-Main">
        <el-container class="container-DeviceList">
            <el-header>
                <el-tabs v-model="activeName" class="demo-tabs el-tabs-DeviceList" @tab-click="handleClick">
                    <el-tab-pane label="全部设备" name="0"></el-tab-pane>
                    <el-tab-pane label="路由器" style="color: #fff;" name="1"></el-tab-pane>
                    <el-tab-pane label="交换机" name="2"></el-tab-pane>
                    <el-tab-pane label="防火墙" name="3"></el-tab-pane>
                    <el-tab-pane label="服务器" name="4"></el-tab-pane>
                </el-tabs>

            </el-header>
            <el-button-group class="ml-4 ">
                    <el-button type="primary" :icon="Grid" />
                    <el-button type="primary" :icon="List" />
                </el-button-group>
            <el-main class="main-Main-DeviceList" max-height="40px" v-loading="Ddevice_List_date.date && Ddevice_List_date.date.length > 0 ? false : true"
                element-loading-text="加载中..." 
    element-loading-background="rgba(122, 122, 122, 0.06)"
                
                >
                <el-card v-for="(item, index) in Ddevice_List_date.date" :key="index" class="card-DeviceList">
                    <template #header>
                        <div class="card-header">
                            <span>{{ item.device_name }}</span>
                        </div>
                    </template>
                </el-card>


            </el-main>
        </el-container>
    </div>
</template>

<script setup>
import { ref, reactive } from 'vue';
import { Grid, List } from '@element-plus/icons-vue'
import { dveiceDateStore } from './Date/index'

const Ddevice_List_date = dveiceDateStore()

const o = ref(0)
const activeName = ref('0')
// 卡片数据

const handleClick = (tab) => {
    Ddevice_List_date.clearData()
    const currentTabName = tab.paneName
    console.log('当前点击的 tab:', currentTabName)
}






</script>
<style scoped>
.device-list-Main,
.common-layout-device-list-Main,
.box-common-layout-device-list-Main {
    width: 100%;
    height: 100%;
    color: #fff;

}


:deep(.el-button:hover) {
    background: none;
}


/* 只修改非激活状态的标签页文字颜色 */
:deep(.el-tabs-DeviceList .el-tabs__item:not(.is-active)) {
    color: #c0ccda;

    /* 非激活状态的颜色 */
}

/* 确保激活状态保持蓝色 */
:deep(.el-tabs-DeviceList .el-tabs__item.is-active) {
    color: #409eff;
    /* 保持激活状态的蓝色 */
}

/* 悬停状态 */
:deep(.el-tabs-DeviceList .el-tabs__item:hover) {
    color: #409eff;
    /* 悬停时变为蓝色 */
}

/* 底部指示条保持蓝色 */
:deep(.el-tabs-DeviceList .el-tabs__active-bar) {
    background-color: #409eff;
}

/* 按钮组 */
:deep(.el-button-group .el-button) {
    margin: 0;
}

.container-DeviceList {
    height: 100%;
}

.main-Main-DeviceList {
    margin-top: 19px;
    display: grid;
    grid-template-columns: repeat(auto-fill, 300px);
    gap: 30px 30px;
    justify-content: center;
    /* overflow-y: auto;     */

}

.card-DeviceList {
    /* margin: 10px; */
    width: 300px;
    height: 40%;
    min-height: 400px;
    /* background-color: #fff; */
    /* color: #000; */
}
</style>: