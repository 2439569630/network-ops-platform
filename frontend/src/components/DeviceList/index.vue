<template>
    <div :class="[$style.deviceListLayout]" v-loading="deviceStore.loading" element-loading-text="加载中..."
            element-loading-background="rgba(0, 0, 0, 0.5)">

        <el-header :class="$style.headerDeviceList">
            <Header />
        </el-header>
        <el-main :class="$style.mainDeviceList">
            <Main />
        </el-main>
        <el-footer :class="$style.footerDeviceList">
            <Footer />
        </el-footer>

    </div>
</template>


<script setup>
import Header from './Header.vue'
import Main from './Main.vue'
import Footer from './Footer.vue';
import { dveiceDateStore } from './Date/index'
import { onMounted } from 'vue'
import axios from 'axios';
import { ElMessage } from 'element-plus'

const deviceStore = dveiceDateStore()

// 页面加载时获取数据
onMounted(async () => {
    // 切换页面数据展示类型 
    console.log(deviceStore.getdataCardType)
    deviceStore.clearData()
    deviceStore.getServerDveiceData()
})




</script>

<style module>
.deviceListLayout {
    height: 100vh;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: #f8f9fa;
}

.headerDeviceList {
    min-height: 120px;
    background: none;
    width: 100%;
    padding: 0 20px; /* Add some padding to align with body */
}

.mainDeviceList {
    flex: 1; /* Take remaining space */
    width: 100%;
    margin-top: 20px;
    padding-top: 0;
    overflow: hidden;
}

.footerDeviceList {
    /* height: 10%; */
    width: 100%;

}

</style>
