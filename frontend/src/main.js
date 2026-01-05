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
import zhCn from 'element-plus/es/locale/lang/zh-cn'


// 引入 fontawesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
// 按需引入你需要的图标
import { faHome,faSitemap,faSync,faPlus,faGlobe,faBell,faServer,faChartLine,faList} from '@fortawesome/free-solid-svg-icons'

library.add(faHome, faPlus,faGlobe,faBell,faSitemap,faSync,faServer,faChartLine,faList)

const app = createApp(App)
const pinia = createPinia()

import axios from './axios/axios.js'

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
app.use(router)
app.use(pinia)
app.use(ElementPlus, {
  locale: zhCn,
})
app.mount('#app')
