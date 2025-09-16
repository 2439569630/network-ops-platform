import { createRouter, createWebHistory } from 'vue-router'
import loginRoutes from './login/intex.js'
import homeRoutes from './home/home.js'
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    ...loginRoutes,
    ...homeRoutes,
    // 重定向
    {
        path: '/',
        redirect: '/home'
    }
  ],
})

export default router
