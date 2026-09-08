import { createApp } from 'vue' // 引入 Vue 的 createApp 方法，用于创建应用实例
import App from './App.vue' // 引入根组件 App
import router from './router' // 引入路由配置
import { createPinia } from 'pinia' // 引入 Pinia，用于状态管理
import { createVuetify } from 'vuetify' // 引入 Vuetify，用于 UI 组件库
import * as components from 'vuetify/components' // 引入 Vuetify 所有组件
import * as directives from 'vuetify/directives' // 引入 Vuetify 所有指令
import '@mdi/font/css/materialdesignicons.css' // 引入 Material Design Icons 图标库 CSS
import 'vuetify/styles' // 引入 Vuetify 样式
// ElementPlus
import ElementPlus from 'element-plus' // 引入 Element Plus UI 组件库
import 'element-plus/dist/index.css' // 引入 Element Plus 样式
import './styles/element-plus-overrides.css' // 引入 Element Plus 的样式覆盖文件（自定义样式）
import zhCn from 'element-plus/es/locale/lang/zh-cn' // 引入 Element Plus 中文语言包


// 引入 fontawesome
import { library } from '@fortawesome/fontawesome-svg-core' // 引入 FontAwesome 核心库
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome' // 引入 FontAwesome Vue 组件
// 按需引入你需要的图标
import { faHome,faSitemap,faSync,faPlus,faGlobe,faBell,faServer,faChartLine,faList} from '@fortawesome/free-solid-svg-icons' // 引入具体的 FontAwesome 图标

// 将图标添加到 FontAwesome 库中，以便在组件中使用
library.add(faHome, faPlus,faGlobe,faBell,faSitemap,faSync,faServer,faChartLine,faList)

const app = createApp(App) // 创建 Vue 应用实例
const pinia = createPinia() // 创建 Pinia 实例

import { cancelAllRequests } from './axios/axios.js' // 引入取消所有请求的方法
import { homeDataStore } from '@/components/home/home/data' // 引入主页数据 Store
import { useDeviceStore } from '@/components/DeviceList/store' // 引入设备列表 Store
import { messageCenterDataStore } from '@/components/MessageCenter/date' // 引入消息中心数据 Store

try {
  // 监听 'auth:force-login' 自定义事件，通常在 token 过期或需要强制重新登录时触发
  window.addEventListener('auth:force-login', async (ev) => {
    // 获取强制登录的原因
    const reason = ev?.detail?.reason ? String(ev.detail.reason) : ''
    // 如果有原因，将其作为查询参数传递给登录页面
    const query = reason ? { reason } : {}
    try {
      try {
        // 取消所有正在进行的网络请求，避免跳转后旧请求回调报错
        cancelAllRequests('force-login')
      } catch {}
      try {
        // 重置主页数据 Store 的状态（如果有 resetForLogout 方法）
        homeDataStore(pinia).resetForLogout?.()
      } catch {}
      try {
        // 重置设备列表 Store 的状态
        useDeviceStore(pinia).resetForLogout?.()
      } catch {}
      try {
        // 重置消息中心 Store 的状态
        messageCenterDataStore(pinia).resetForLogout?.()
      } catch {}
      try {
        // 清除 session storage 中的权限和会话缓存
        sessionStorage.removeItem('auth:session_cache:v1')
        sessionStorage.removeItem('auth:permissions_cache:v1')
      } catch {}
      // 跳转到登录页面，并携带查询参数
      await router.replace({ path: '/login', query })
    } catch {}
  })
} catch {}

// 在main.js或组件中
export default {
  mounted() {
    this.$nextTick(() => {
      // 创建性能观察者，用于监控页面性能指标
      const observer = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          console.log(`${entry.name}: ${entry.duration}ms`)
        })
      })
      // 开始观察 'measure' 类型的性能条目
      observer.observe({entryTypes: ['measure']})
    })
  }
}
app.config.performance = true // 开启性能监测
const vuetify = createVuetify({
  components,
  directives,
})
// 全局注册组件
app.component('font-awesome-icon', FontAwesomeIcon)
// 安装 Vuetify 插件
app.use(vuetify)
// 安装 Pinia 插件
app.use(pinia)
// 安装 Router 插件
app.use(router)
// 安装 Element Plus 插件，并设置语言为中文
app.use(ElementPlus, {
  locale: zhCn,
})
// 挂载应用到 id 为 'app' 的 DOM 元素上
app.mount('#app')
