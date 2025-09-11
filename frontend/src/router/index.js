import { createRouter, createWebHistory } from 'vue-router'
import loginRoutes from './login/intex.js'
const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    ...loginRoutes,
  ],
})

export default router
