import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createPinia } from 'pinia'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
// ElementPlus
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import './styles/element-plus-overrides.css'
import zhCn from 'element-plus/es/locale/lang/zh-cn'


// 引入 fontawesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
// 按需引入你需要的图标
import { faHome,faSitemap,faSync,faPlus,faGlobe,faBell,faServer,faChartLine,faList} from '@fortawesome/free-solid-svg-icons'

library.add(faHome, faPlus,faGlobe,faBell,faSitemap,faSync,faServer,faChartLine,faList)

const app = createApp(App)
const pinia = createPinia()

import { cancelAllRequests } from './axios/axios.js'
import { homeDataStore } from '@/components/home/home/data'
import { useDeviceStore } from '@/components/DeviceList/store'
import { messageCenterDataStore } from '@/components/MessageCenter/date'

try {
  window.addEventListener('auth:force-login', async (ev) => {
    const reason = ev?.detail?.reason ? String(ev.detail.reason) : ''
    const query = reason ? { reason } : {}
    try {
      try {
        cancelAllRequests('force-login')
      } catch {}
      try {
        homeDataStore(pinia).resetForLogout?.()
      } catch {}
      try {
        useDeviceStore(pinia).resetForLogout?.()
      } catch {}
      try {
        messageCenterDataStore(pinia).resetForLogout?.()
      } catch {}
      try {
        sessionStorage.removeItem('auth:session_cache:v1')
        sessionStorage.removeItem('auth:permissions_cache:v1')
      } catch {}
      await router.replace({ path: '/login', query })
    } catch {}
  })
} catch {}

// 在main.js或组件中
export default {
  mounted() {
    this.$nextTick(() => {
      const observer = new PerformanceObserver((list) => {
        list.getEntries().forEach((entry) => {
          console.log(`${entry.name}: ${entry.duration}ms`)
        })
      })
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
app.use(vuetify)
app.use(pinia)
app.use(router)
app.use(ElementPlus, {
  locale: zhCn,
})
app.mount('#app')
