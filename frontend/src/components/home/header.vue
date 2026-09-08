<template>
    <!-- 菜单栏 -->
    <div class="header">
        <div class="center">
            <div class="logo">
                <font-awesome-icon icon="fas fa-sitemap" />
                <h1>NetAutomation</h1>
            </div>
            <div class="nav"></div>
            <div class="login"></div>
        </div>
    </div>
</template>
<script setup>

</script>
<style scoped>
.header {
    height: 80px;
    /* background: rgba(26, 54, 93, 0.9); */
    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
    /* 固定菜单栏 */
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    padding: 10px;
}
.center {
    height: 100%;
    max-width: 1800px;
    margin: 0 auto;
    padding: 0 32px;
    display: flex;
}

.logo {
    flex: 1;
    display: flex;
    align-items: center;
    justify-items: center;
    color: var(--text);
}
.logo > svg {
    color: var(--accent);
}
.nav {
    flex: 0;
}
.login {
    flex: 1;
   
}

.logo svg {
    font-size: 40px;
    color: #fff;
}

/* 电脑端媒体 */
/* 媒体查询 */
/* 小屏 */
@media (min-width: 768px) {
    .center {
        margin: 0;
        padding: 0;

    }
}


/* 移动端媒体 */
/* 媒体查询 */

/* 大屏 */
@media (max-width: 991px) {
    .logo > h1 {
        display: none;
    }
    .center {
        margin: 0;
        padding: 0;

    }
}

</style>