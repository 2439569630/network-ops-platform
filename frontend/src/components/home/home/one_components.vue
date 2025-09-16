<template>
    <div class="bigBox">
        <div class="left">
            <h1>网络设备自动化运维平台</h1>
        </div>
        <div class="right">
            <v-btn>
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

.left,
.right {
    width: auto;
    height: 100%;
    display: flex;
    align-items: center;
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

}
</style>