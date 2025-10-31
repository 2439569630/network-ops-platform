<template>
    <div class="DeviceList-common-layout">
        <el-container class="container">
            <el-header class="header-DeviceList">
                <Header />
            </el-header>

            <el-main class="Main-DeviceList">
                <Main />
            </el-main>
            <el-footer class="footer-DeviceList">
                <Footer />
            </el-footer>
        </el-container>
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
    // 先清空数据
    deviceStore.clearData()
    await axios.get('/user/device/get?type=0')
        .then((response) => {
            if (response.data) {
                deviceStore.addData(response.data)
            }
        }).catch((error) => {
            console.error('获取设备信息失败:', error)
            ElMessage({
                message: error.response.data?.message ,
                type: 'error'
            })
        })


})




</script>

<style scoped>
.DeviceList-common-layout {
    height: calc(100vh - 40px);
    /* 使用视口高度作为基准 */
    width: 100%;
    display: flex;

}

.header-DeviceList {
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}
</style>