<!-- 这是卡片头部标题组件 -->
<template>
    <div class="box">
        <div class="title_left">
            <div class="icon">
                <slot name="icon"></slot>
            </div>
            <div class="title">
                <h3>
                    <slot name="title"></slot>
                </h3>
            </div>
        </div>
        <!-- 操作按钮 -->
        <div class="btn" v-if="$slots.btn">
            <v-btn class="btn" rounded="lg" size="large" block :ripple="true" color="var(--accent)">
                <slot name="btn"></slot>
            </v-btn>

        </div>
    </div>
</template>
<script>

</script>
<style>
.box {
    width: 100%;
    padding: 10px;
    display: flex;
    background: rgba(26, 54, 93, 0.8);
    align-items: center;
    justify-content: space-between;
    font-family: "微软雅黑";
border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}



.title_left {
    display: flex;
    align-items: center;
    margin-left: 10px;
}

.title_left>.title {
    margin-left: 10px;
    color: var(--text);
}



.btn {
    color: var(--text);
    font-size: 0.9rem;
}
</style>