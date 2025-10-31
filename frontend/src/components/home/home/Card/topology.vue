<template>
    <BaseCard>
        <template #icon>
            <font-awesome-icon class="icon" icon="fas fa-sitemap" />
        </template>
        <template #title>
            网络拓扑视图
        </template>
        <template #btn>
            全屏查看
        </template>
    </BaseCard>
</template>
<script setup>
import BaseCard from './BaseTopCard.vue'
</script>
<style scoped></style>