<template >
  <div class="common-layout">
    <!-- Mobile Top Navigation -->
    <div v-if="isMobile" class="mobile-topbar">
      <div class="mobile-brand">
          <span class="brand-text">BISE System</span>
      </div>
      <el-button 
        class="mobile-menu-toggle" 
        :class="{ 'is-active': menuExpanded }"
        text 
        circle 
        @click="menuExpanded = !menuExpanded"
      >
        <el-icon :size="24" v-if="!menuExpanded"><Menu /></el-icon>
        <el-icon :size="24" v-else><Close /></el-icon>
      </el-button>
    </div>
    
    <!-- Mobile Menu Overlay -->
    <el-collapse-transition>
      <div v-if="isMobile && menuExpanded" class="mobile-menu-wrapper">
        <div class="mobile-menu-content">
            <LEFT variant="mobile" @navigated="menuExpanded = false" />
        </div>
        <div class="mobile-menu-backdrop" @click="menuExpanded = false"></div>
      </div>
    </el-collapse-transition>

    <el-container>
      <el-container class="container">
        <el-aside v-if="!isMobile" class="aside"> <LEFT /> </el-aside>
        <el-main class="main"> <RouterView></RouterView> </el-main>
      </el-container>
    </el-container>
  </div>
</template>
<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue' // 引入 Vue 生命周期钩子和响应式 API
import LEFT from './left/left.vue' // 引入左侧导航栏组件
import { homeDataStore } from '@/components/home/home/data' // 引入主页数据 Store
import { Menu, Close } from '@element-plus/icons-vue' // 引入菜单图标

const store = homeDataStore() // 获取 Store 实例
const menuExpanded = ref(false) // 移动端菜单展开状态
const isMobile = ref(false) // 是否为移动端视图
let mobileMediaQuery = null // 媒体查询对象
let mobileMediaListener = null // 媒体查询监听器

// 组件挂载时执行
onMounted(() => {
  store.syncAuthFromToken() // 同步认证信息
  if (!store.isSuper) void store.fetchPermissions() // 如果不是超级管理员，获取权限列表

  // 初始化移动端媒体查询 (宽度小于等于 900px 视为移动端)
  mobileMediaQuery = window.matchMedia('(max-width: 900px)')
  mobileMediaListener = () => {
    isMobile.value = mobileMediaQuery.matches // 更新 isMobile 状态
    if (!isMobile.value) menuExpanded.value = false // 切换到桌面端时，自动关闭菜单
  }
  mobileMediaListener() // 初始化执行一次

  // 添加媒体查询监听器（兼容旧版浏览器）
  if (typeof mobileMediaQuery.addEventListener === 'function') {
    mobileMediaQuery.addEventListener('change', mobileMediaListener)
  } else {
    mobileMediaQuery.addListener(mobileMediaListener)
  }
})

// 组件销毁前执行
onBeforeUnmount(() => {
  if (!mobileMediaQuery || !mobileMediaListener) return
  // 移除媒体查询监听器
  if (typeof mobileMediaQuery.removeEventListener === 'function') {
    mobileMediaQuery.removeEventListener('change', mobileMediaListener)
  } else {
    mobileMediaQuery.removeListener(mobileMediaListener)
  }
  mobileMediaQuery = null
  mobileMediaListener = null
})
</script>
<style scoped>
.common-layout{
    width: 100vw;
    height: 100vh;
    color: #fff;
    overflow: hidden; /* Prevent body scroll when menu is open? handled via overlay */
}

.aside {
    width: clamp(220px, 15vw, 300px);
    min-width: 220px;
    height: 100vh;
    overflow-y: auto;
    border-right: none;
    /* background: rgba(45, 55, 72, 0.6); */
}
.main {
    width: auto;
    flex: 1;
    /* background: rgba(45, 55, 72, 0.6); */
    height: 100vh;
    padding: 0;
    overflow-y: auto;
}

.common-layout :deep(.el-main) {
    padding: 0;
}

/* Mobile Styles */
@media (max-width: 900px) {
    .common-layout {
        box-sizing: border-box;
        padding-top: 56px; /* Match header height */
    }

    /* Top Bar */
    .mobile-topbar {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 1000; /* Lower than Element Plus (2000+) */
        height: 56px;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 0 16px;
        background: #fff;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
    }

    .mobile-brand {
        font-size: 18px;
        font-weight: 600;
        color: #1e3a8a;
        display: flex;
        align-items: center;
    }

    .mobile-menu-toggle {
        width: 40px;
        height: 40px;
        color: #606266;
        transition: all 0.3s;
    }
    
    .mobile-menu-toggle.is-active {
        transform: rotate(90deg);
        color: #1e3a8a;
    }

    /* Menu Wrapper */
    .mobile-menu-wrapper {
        position: fixed;
        top: 56px;
        left: 0;
        right: 0;
        bottom: 0;
        z-index: 999; /* Below header */
        display: flex;
        flex-direction: column;
    }

    .mobile-menu-content {
        background: #fff; /* Use white background for better readability on mobile or match theme */
        max-height: 70vh;
        overflow-y: auto;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        border-bottom-left-radius: 16px;
        border-bottom-right-radius: 16px;
        /* Ensure it sits on top of backdrop */
        position: relative;
        z-index: 2;
    }

    /* Backdrop */
    .mobile-menu-backdrop {
        flex: 1;
        background: rgba(0, 0, 0, 0.4);
        backdrop-filter: blur(2px);
    }

    .main {
        height: calc(100vh - 56px);
    }
}
</style>
