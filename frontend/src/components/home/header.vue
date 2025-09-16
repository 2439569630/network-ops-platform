<template>
    <div class="head">
        <div class="container">
            <nav>
                <div class="left">
                    <font-awesome-icon style="color: var(--accent);" icon="fas fa-sitemap" />
                    <span>NetAutomation</span>
                </div>
                <div class="center">
                    <ul>
                        <li @click="goToHome()"><font-awesome-icon icon="far fa-home" />首页</li>
                        <li @click="goToDevice()">设备管理</li>
                        <li>网络拓扑</li>
                        <li>自动化任务</li>
                        <li>性能监控</li>
                        <li>系统设置</li>
                    </ul>
                </div>
                <div class="right">
                    
                </div>
            </nav>
        </div>
    </div>
</template>
<script setup>
import router  from '@/router';

const goToHome = () => {
    router.push('/home');
}
const goToDevice = () => {
    router.push('/device');
}

</script>
<style scoped>
.head {
    width: 100%;
    height: 70px;
    background: rgba(26, 54, 93, 0.9);
    padding: 12px;
    display: flex;

    box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
}

.container {
    width: 100%;
    max-width: 1800px;
    margin: 0 auto;
    padding: 0 20px;

}

nav {
    width: 100%;
    height: 100%;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.head .left {
    width: 25%;
    height: 100%;
    min-width: 250px;
    font-family: "Font Awesome 6 Free";
    display: flex;
    align-items: center;
    font-size: 1.8rem;
    font-weight: 700;
    color: var(--text);
}


.head .center {
    width: 60%;
    height: 100%;
    min-width: 666px;
    /* background: yellow; */
}

.head .right {
    width: 20%;
    height: 100%;
    /* background: blue; */
}

.head .center ul {
    width: 100%;
    height: 100%;
    display: flex;
    justify-content: center;
    align-items: center;
    list-style: none;

}

.head .center ul li {
    margin: 0 20px;
    font-size: 1.1rem;
    color: var(--text);
    cursor: pointer;
    position: relative;
    padding: 10px 0;
    color: var(--text);
    text-decoration: none;
    font-weight: 500;
    transition: color 0.3s;
    display: flex;
    align-items: center;
}
.head .center ul li:hover {
    color: var(--accent);
}
</style>