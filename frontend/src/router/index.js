import { createRouter, createWebHistory } from 'vue-router'
import loginRoutes from '@/router/login/index.js'
import homeRoutes from '@/router/user/index.js'
import { jwtDecode } from 'jwt-decode'
import Cookies from 'js-cookie'
import { ElNotification } from 'element-plus'

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

    // 权限检查
    const token = Cookies.get('token');
    if (token) {
        try {
            const decoded = jwtDecode(token);
            const userRole = Number(decoded.permission_level);

            // 如果路由定义了 roles 且当前用户角色不在允许列表中
            if (to.meta.roles && !to.meta.roles.includes(userRole)) {
                ElNotification({
                    title: '权限不足',
                    message: '您没有权限访问该页面',
                    type: 'error',
                });
                
                if (from.path === '/login') {
                    // 如果是从登录页来的（即刚登录），说明用户没有首页权限，或者首页配置错误
                    // 此时应该留在登录页或清除 Token
                    Cookies.remove('token');
                    next('/login');
                } else {
                     // 否则保持在当前页面
                     next(false);
                }
                return;
            }
        } catch (e) {
            console.error("Token decode error", e);
            // Token 无效，可能需要重定向到登录
        }
    } else if (to.path.startsWith('/user')) {
        // 未登录访问受保护页面
        next('/login');
        return;
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
