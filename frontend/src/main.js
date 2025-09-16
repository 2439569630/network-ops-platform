import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

// 引入 fontawesome
import { library } from '@fortawesome/fontawesome-svg-core'
import { FontAwesomeIcon } from '@fortawesome/vue-fontawesome'
// 按需引入你需要的图标
import { faHome,faSitemap,faSync,faPlus } from '@fortawesome/free-solid-svg-icons'
import { faHome as faHomeRegular } from '@fortawesome/free-regular-svg-icons'

library.add(faHome, faHomeRegular, faPlus)
library.add(faSitemap)
library.add(faSync)
const app = createApp(App)

const vuetify = createVuetify({
  components,
  directives,
})
// 全局注册组件
app.component('font-awesome-icon', FontAwesomeIcon)
app.use(vuetify)
app.use(router)
app.mount('#app')
