<template >
  <div class="common-layout">
    <el-container>
      <el-container class="container">
        <el-aside class="aside"> <LEFT /> </el-aside>
        <el-main class="main"> <RouterView></RouterView> </el-main>
      </el-container>
    </el-container>
  </div>
</template>
<script setup>
import { onMounted } from 'vue'
import LEFT from './left/left.vue'
import { homeDataStore } from '@/components/home/home/data'

const store = homeDataStore()

onMounted(() => {
  store.syncAuthFromToken()
  if (!store.isSuper) void store.fetchPermissions()
})
</script>
<style scoped>
.common-layout{
    width: 100vw;
    height: 100vh;
    color: #fff;
}

.aside {
    width: clamp(220px, 15vw, 300px);
    min-width: 220px;
    height: 100vh;
    border-right: none;
    /* background: rgba(45, 55, 72, 0.6); */
}
.main {
    width: auto;
    flex: 1;
    /* background: rgba(45, 55, 72, 0.6); */
    height: 100vh;
    padding: 0;
}

.common-layout :deep(.el-main) {
    padding: 0;
}

@media (max-width: 900px) {
    .aside {
        width: 64px;
        min-width: 64px;
    }

    .aside :deep(.el-menu-item span),
    .aside :deep(.el-sub-menu__title span) {
        display: none;
    }

    .aside :deep(.el-menu-item),
    .aside :deep(.el-sub-menu__title) {
        justify-content: center;
        padding-left: 0 !important;
        padding-right: 0 !important;
    }
}
</style>
