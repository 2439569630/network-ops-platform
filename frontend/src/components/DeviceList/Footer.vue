<template>
    <div class="box-DeviceList-Footer"  v-if="Ddevice_List_date.dataLength()">
        <el-pagination :background="hasBackground" layout="prev, pager, next" :total="1000" />
    </div>

</template>

<script setup lang="ts">
import { ref } from 'vue'
import { dveiceDateStore } from './Date/index'

const Ddevice_List_date = dveiceDateStore()
const hasBackground = ref(true)
</script>

<style scoped>
.box-DeviceList-Footer {
    width: 100%;
    height: 50px;
    display: flex;
    justify-content: center;
    align-items: center;
    background: #fff;
    border-radius: 0 0 12px 12px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

</style>