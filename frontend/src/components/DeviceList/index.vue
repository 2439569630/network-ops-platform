<template>
    <div ref="layoutRef" :class="[$style.deviceListLayout, { [$style.isMobile]: isMobile }]">

        <el-header ref="headerRef" :class="$style.headerDeviceList">
            <Header />
        </el-header>
        <div v-if="isMobile" :class="$style.headerSpacer"></div>
        <el-main
            :class="$style.mainDeviceList"
            v-loading="deviceStore.loading"
            element-loading-text="加载中..."
            element-loading-background="rgba(0, 0, 0, 0.5)"
        >
            <Main />
        </el-main>
        <el-footer :class="$style.footerDeviceList" v-if="!isMobile">
            <Footer />
        </el-footer>

    </div>
</template>


<script setup>
import Header from './Header.vue'
import Main from './Main.vue'
import Footer from './Footer.vue';
import { useDeviceStore } from './store'
import { onMounted, onBeforeUnmount, ref, nextTick, watch } from 'vue'

const deviceStore = useDeviceStore()
const isMobile = ref(false)
let mobileMediaQuery = null
let mobileMediaListener = null

const layoutRef = ref(null)
const headerRef = ref(null)
let headerResizeObserver = null

const setHeaderHeightVar = () => {
    const layoutEl = layoutRef.value
    const headerEl = headerRef.value?.$el || headerRef.value
    if (!layoutEl || !headerEl) return
    const height = headerEl.offsetHeight || 0
    layoutEl.style.setProperty('--device-header-height', `${height}px`)
}

const startObserveHeaderHeight = () => {
    const headerEl = headerRef.value?.$el || headerRef.value
    if (!headerEl) return
    if (headerResizeObserver) return
    headerResizeObserver = new ResizeObserver(() => setHeaderHeightVar())
    headerResizeObserver.observe(headerEl)
    setHeaderHeightVar()
}

const stopObserveHeaderHeight = () => {
    if (headerResizeObserver) {
        headerResizeObserver.disconnect()
        headerResizeObserver = null
    }
    const layoutEl = layoutRef.value
    if (layoutEl) layoutEl.style.setProperty('--device-header-height', `0px`)
}

// 页面加载时获取数据
onMounted(async () => {
    // 切换页面数据展示类型 
    console.log(deviceStore.getdataCardType)
    // deviceStore.clearData() // 不需要清空，因为是全局连接
    // deviceStore.getServerDveiceData() // 不需要手动连接，App.vue 已处理
    // 可以在这里刷新一下以确保数据最新，或者设置正确的 Filter Type
    deviceStore.refreshData()

    // Mobile Check
    mobileMediaQuery = window.matchMedia('(max-width: 768px)')
    mobileMediaListener = () => {
        isMobile.value = mobileMediaQuery.matches
        // 如果是手机端，默认设置为无限滚动模式（即一页显示所有，或 Store 支持无限加载）
        // 目前简单实现：手机端不分页，显示全部
        if (isMobile.value) {
            deviceStore.setPageSize(1000) // 临时方案：设置一个大 PageSize
        } else {
            deviceStore.setPageSize(10) // PC端恢复默认
        }
    }
    mobileMediaListener()
    if (mobileMediaQuery.addEventListener) {
        mobileMediaQuery.addEventListener('change', mobileMediaListener)
    } else {
        mobileMediaQuery.addListener(mobileMediaListener)
    }

    await nextTick()
    if (isMobile.value) startObserveHeaderHeight()
})

onBeforeUnmount(() => {
    if (mobileMediaQuery && mobileMediaListener) {
        if (mobileMediaQuery.removeEventListener) {
            mobileMediaQuery.removeEventListener('change', mobileMediaListener)
        } else {
            mobileMediaQuery.removeListener(mobileMediaListener)
        }
    }
    stopObserveHeaderHeight()
})

watch(isMobile, async (val) => {
    await nextTick()
    if (val) startObserveHeaderHeight()
    else stopObserveHeaderHeight()
})
</script>

<style module>
.deviceListLayout {
    height: 100vh;
    width: 100%;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: #f8f9fa;
    --device-header-height: 0px;
}

.deviceListLayout.isMobile {
    height: auto;
    min-height: 100vh;
    overflow: visible; /* Let body scroll */
}

.headerDeviceList {
    min-height: 120px;
    background: none;
    width: 100%;
    padding: 0 20px; /* Add some padding to align with body */
    height: auto !important;
}

.isMobile .headerDeviceList {
    min-height: auto;
    padding: 0;
    position: fixed;
    top: 56px;
    left: 0;
    right: 0;
    z-index: 900;
    background: #fff;
    height: auto !important;
}

.headerSpacer {
    display: none;
}

.isMobile .headerSpacer {
    display: block;
    height: var(--device-header-height);
    flex-shrink: 0;
}

.mainDeviceList {
    flex: 1; /* Take remaining space */
    width: 100%;
    margin-top: 20px;
    padding-top: 0;
    overflow: hidden;
}

.isMobile .mainDeviceList {
    overflow: visible;
    margin-top: 0;
    padding: 0;
    flex: none; /* Auto height */
}

.footerDeviceList {
    /* height: 10%; */
    width: 100%;

}

</style>
