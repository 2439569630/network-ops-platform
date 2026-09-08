<template>
    <div class="common-layout-404">
        <el-empty description="404 您访问的页面不存在">
            <el-button @click="goBack">返回上页</el-button>
            <el-button type="primary" @click="goHome">返回首页</el-button>
        </el-empty>
    </div>
</template>
<script setup>
import router from '@/router';

const goBack = () => {
    router.go(-1);
}
const goHome = () => {
    router.push('/');
}
</script>

<style scoped>
.common-layout-404 {
    width: 100%;
    height: 100vh;
    display: flex;
    justify-content: center;
    align-items: center;
    background-color: #fff;
}
</style>
