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
import { onBeforeUnmount, onMounted, ref } from 'vue'
import LEFT from './left/left.vue'
import { homeDataStore } from '@/components/home/home/data'
import { Menu, Close } from '@element-plus/icons-vue'

const store = homeDataStore()
const menuExpanded = ref(false)
const isMobile = ref(false)
let mobileMediaQuery = null
let mobileMediaListener = null

onMounted(() => {
  store.syncAuthFromToken()
  if (!store.isSuper) void store.fetchPermissions()

  mobileMediaQuery = window.matchMedia('(max-width: 900px)')
  mobileMediaListener = () => {
    isMobile.value = mobileMediaQuery.matches
    if (!isMobile.value) menuExpanded.value = false
  }
  mobileMediaListener()
  if (typeof mobileMediaQuery.addEventListener === 'function') {
    mobileMediaQuery.addEventListener('change', mobileMediaListener)
  } else {
    mobileMediaQuery.addListener(mobileMediaListener)
  }
})

onBeforeUnmount(() => {
  if (!mobileMediaQuery || !mobileMediaListener) return
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
