<template>
    <BaseCard>
        <template #icon>
            <font-awesome-icon icon="fas fa-server" />
        </template>
        <template #title>
            设备状态
        </template>
        <template #btn>
            设备列表
        </template>
    </BaseCard>
</template>
<script setup>
import BaseCard from './BaseTopCard.vue';
</script>