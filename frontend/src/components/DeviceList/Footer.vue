<template>
    <div class="box-DeviceList-Footer"  v-if="Ddevice_List_date.date && Ddevice_List_date.date.length > 0">
        <el-pagination :background="hasBackground" layout="prev, pager, next" :total="1000" />
    </div>

</template>

<script setup>
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
}

</style>