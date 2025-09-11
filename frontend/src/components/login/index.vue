<template>
    <div class="box">
        <slot name="Login"></slot>
    </div>
</template>
<script setup>
import Login from '@/components/login/index.vue'

</script>
<style scoped>
.box {
    width: 100%;
    height: 100vh;
    background: #f0f2f5;
    /* 隐藏滚动条 */
    overflow: hidden;
}


</style>