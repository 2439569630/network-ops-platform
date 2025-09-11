import { createApp } from 'vue'
import App from './App.vue'
import router from './router'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'
const app = createApp(App)

const vuetify = createVuetify({
  components,
  directives,
})
app.use(vuetify)
app.use(router)
app.mount('#app')
