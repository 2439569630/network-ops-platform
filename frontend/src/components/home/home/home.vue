<template>
    <div class="box">
        <div class="container">
            <div class="one">
                <one />
            </div>

        </div>
    </div>
</template>
<script setup>
import one from "./one_components.vue"
</script>
<style scoped>
.box {
    position: absolute;
    top: 70px;
    left: 0;
    bottom: 0;
    right: 0;
    height: calc(100vh - 70px);
    /* 隐藏滚动条 */
    overflow: hidden;
    background: linear-gradient(135deg, var(--dark), var(--primary));
}
.container {
    width: 100%;
    max-width: 1800px;
    height: 100%;
    margin: 0 auto;
    padding: 0 32px;
    box-sizing: border-box;
    color: var(--text-light);
    display: flex;
    flex-direction: column;
}

.one {
    width: 100%;
    height: 10%;
    min-height: 50px;
    margin-top: 30px;

}
</style>