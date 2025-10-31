<template>
    <div class="bigBox">
        <div class="left">
            <h1>网络设备自动化运维平台</h1>
        </div>
        <div class="right">
            <v-btn class="btn">
                <template v-slot:prepend>
                    <font-awesome-icon icon="fas fa-sync" />
                </template>
                刷新数据
            </v-btn>

            <v-btn>
                <template v-slot:prepend>
                    <font-awesome-icon icon="fas fa-plus" />
                </template>

                新建任务</v-btn>
        </div>
    </div>
</template>
<script>
</script>
<style scoped>
.bigBox {
    width: 100%;
    height: 100%;
    display: flex;
    justify-content: space-between;
}
h1 {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--text);
    
    /* 过渡 */
    transition: all 0.3s ease-in-out;
}

h1:hover {
    transform: translateY(-10px) scale(1.1);
    color: var(--accent);
}
.left,
.right {
    width: auto;
    height: 100%;
    display: flex;
    align-items: center;
    color: var(--text);
}

.left {
    font-size: 1.2rem;
    font-weight: 700;
    color: var(--text);
}
.right button {
    height: 60%;
}


.right button {
    background-color: var(--accent);
    margin-left: 20px;
    height: 70%;
    min-height: 44px;
    font-size: 0.9rem;
}



/* 媒体查询 */
/* 小屏 */
@media (max-width: 991px) {
    h1 {
        /* 隐藏不保留dom */
        display: none;
        transform: translateY(-10px);
    }

    .bigBox,.container {
        margin: 0;
        padding: 0;
    }

}


</style>