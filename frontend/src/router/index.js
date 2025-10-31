import { createRouter, createWebHistory } from 'vue-router'
import loginRoutes from './login/index.js'
import homeRoutes from '@/router/user/index.js'

// 路径状态导入
import routerPathStatus from '@/router/StatusPageRouters/index.js'



const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL),
    routes: [
        ...loginRoutes,
        ...homeRoutes,
        ...routerPathStatus,
        {
            path: '/',
            redirect: '/login'
        }
    ],
})


// 路由守卫
router.beforeEach((to, from, next) => {
    // 设置页面标题
    if (to.meta.title) {
        document.title = to.meta.title
    }

    // 修复路由存在性检查
    if (to.matched.length === 0) {
        // 使用 next 进行重定向，避免循环导航
        next('/404')
    } else {
        // 确保始终调用 next()
        next()
    }
})



export default router
