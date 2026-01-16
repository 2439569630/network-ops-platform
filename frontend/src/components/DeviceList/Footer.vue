<template>
    <div class="box-DeviceList-Footer"  v-if="deviceStore.dataLength()">
        <el-pagination 
            v-model:current-page="deviceStore.currentPage"
            v-model:page-size="deviceStore.pageSize"
            :page-sizes="[10, 20, 50, 100]"
            :background="hasBackground" 
            layout="total, sizes, prev, pager, next, jumper" 
            :total="deviceStore.dataLength()" 
        />
    </div>

</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useDeviceStore } from './store'

const deviceStore = useDeviceStore()
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