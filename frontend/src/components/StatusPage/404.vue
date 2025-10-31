<template>
    <div class="common-layout-404">
        <el-container>
            <el-header>
                <h2 class="shadow-title">404 您访问的页面不存在。</h2>
            </el-header>
            <el-main class="button-404"><el-button  @click="goBack()">返回上页</el-button><el-button type="primary" @click="goLogin()">返回登录</el-button></el-main>
        </el-container>
    </div>
</template>
<script setup>
import router from '@/router';

const goBack = () => {
    router.go(-1);
}
const goLogin = () => {
    router.push('/login');
}


</script>

<style scoped>
.common-layout-404 {
    width: 50vw;
    height: 100vh;
    margin: 0 auto;
    color: white;
    display: grid;
    align-content: space-around;
}
.common-layout-404 h2 {
    font-size: 50px;
    text-align: center;
    margin: 0;
    padding: 0;
}
.shadow-title {
    text-shadow: 
        2px 2px 4px rgba(0, 0, 0, 0.5),
        0 0 20px rgba(255, 255, 255, 0.3);
    /* 可选的阴影效果变体 */
    text-shadow: 3px 3px 6px rgba(0, 0, 0, 0.7); /* 更强的阴影 */
    text-shadow: 0 0 10px rgba(255, 255, 255, 0.8), 0 0 20px rgba(255, 255, 255, 0.6); /* 发光效果 */
}

.button-404 {
    margin-top: 50px;
    display: flex;
    justify-content: center;
    align-items: center;
}
</style>
