import { createRouter, createWebHistory } from 'vue-router' // 引入 Vue Router 的创建方法和 History 模式
import loginRoutes from '@/router/login/index.js' // 引入登录模块的路由配置
import homeRoutes from '@/router/user/index.js' // 引入用户模块的路由配置
import { ElNotification } from 'element-plus' // 引入 Element Plus 的通知组件
import { homeDataStore } from '@/components/home/home/data' // 引入主页数据 Store，用于获取用户权限信息

// 路径状态导入
import routerPathStatus from '@/router/StatusPageRouters/index.js' // 引入状态页（如 404）的路由配置



const router = createRouter({
    history: createWebHistory(import.meta.env.BASE_URL), // 使用 Web History 模式，基础路径从环境变量获取
    routes: [
        ...loginRoutes, // 展开登录路由
        ...homeRoutes, // 展开用户路由
        ...routerPathStatus, // 展开状态页路由
        {
            path: '/',
            redirect: '/login' // 根路径重定向到登录页
        }
    ],
})

// 辅助函数：连接父路径和子路径，避免多余的斜杠
const joinPaths = (base, child) => {
    const b = String(base || '').replace(/\/+$/, '')
    const c = String(child || '').replace(/^\/+/, '')
    return `${b}/${c}`
}

// 扁平化用户路由配置，用于后续计算用户可访问的第一个路径
const flattenUserRouteCandidates = () => {
    const out = []
    // 递归访问路由树
    const visit = (routes, basePath = '') => {
        (routes || []).forEach(r => {
            const path = r?.path
            if (typeof path !== 'string') return
            // 计算完整路径
            const fullPath = path.startsWith('/') ? path : joinPaths(basePath, path)
            // 如果路径包含参数（:）或通配符（*），则继续递归子路由，但不将当前路径加入候选列表
            if (fullPath.includes(':') || fullPath.includes('*')) {
                if (Array.isArray(r.children) && r.children.length > 0) {
                    visit(r.children, fullPath)
                }
                return
            }
            // 筛选以 /user 开头的路径，排除 /user 自身
            if (fullPath.startsWith('/user') && fullPath !== '/user') {
                out.push({ path: fullPath, meta: r.meta || {} })
            }
            // 继续递归子路由
            if (Array.isArray(r.children) && r.children.length > 0) {
                visit(r.children, fullPath)
            }
        })
    }
    visit(homeRoutes, '')
    // 去重
    const uniq = []
    const seen = new Set()
    out.forEach(r => {
        if (!seen.has(r.path)) {
            seen.add(r.path)
            uniq.push(r)
        }
    })
    // 定义优先跳转的路径列表
    const prioritize = ['/user/dashboard', '/user/home', '/user/message']
    // 对路由进行排序，优先路径排在前面
    uniq.sort((a, b) => {
        const ia = prioritize.indexOf(a.path)
        const ib = prioritize.indexOf(b.path)
        if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
        return 0
    })
    return uniq
}

const userRouteCandidates = flattenUserRouteCandidates() // 获取扁平化后的用户路由候选列表

// 检查用户是否有权限访问特定路由的 meta 配置
const canAccessRouteMeta = (meta, ctx) => {
    const m = meta || {}
    // 检查权限标识 (perms)
    if (m.perms && Array.isArray(m.perms) && m.perms.length > 0) {
        if (ctx.isSuper) return true // 超级管理员拥有所有权限
        return m.perms.some(p => ctx.userPerms.includes(String(p)))
    }
    // 检查角色代码 (roleCodes)
    if (m.roleCodes && Array.isArray(m.roleCodes) && m.roleCodes.length > 0) {
        if (ctx.isSuper) return true
        return m.roleCodes.some(rc => ctx.roleCodes.includes(String(rc).toLowerCase()))
    }
    // 检查角色 ID (roles) - 旧逻辑兼容
    if (m.roles && Array.isArray(m.roles) && m.roles.length > 0) {
        return m.roles.includes(ctx.userRole)
    }
    return true // 如果没有配置权限限制，默认允许访问
}

// 获取用户有权访问的第一个路径，作为默认跳转路径
const getFirstAccessibleUserPath = (ctx) => {
    for (const r of userRouteCandidates) {
        if (canAccessRouteMeta(r.meta, ctx)) return r.path
    }
    return '/login' // 如果没有可访问路径，跳转到登录页
}

// 根据 Store 中的用户信息，计算默认跳转路径
const getDefaultAuthedPath = async (store) => {
    const roleCodes = Array.isArray(store?.roleCodes) ? store.roleCodes.map(r => String(r).toLowerCase()) : []
    const isSuper = typeof store?.isSuperAdmin === 'function'
        ? store.isSuperAdmin()
        : Boolean(store?.isSuper)
    // 根据角色代码映射用户角色 ID (兼容旧逻辑)
    const userRole = isSuper ? 0 : (roleCodes.includes('yunwei') ? 1 : 2)
    // 获取用户权限列表
    const perms = isSuper ? [] : await store.fetchPermissions()
    const ctx = { roleCodes, isSuper, userRole, userPerms: Array.isArray(perms) ? perms.map(String) : [] }
    return getFirstAccessibleUserPath(ctx)
}

// 判断是否应该跳过“登录页会话检查”
// 防止在强制登录跳转或刚刚强制登录后，因会话检查导致的循环或错误
const shouldSkipLoginEnsureSession = (to) => {
    const reason = String(to?.query?.reason || '').trim()
    if (reason) return true
    try {
        const ts = Number(sessionStorage.getItem('auth:force_login_at') || 0)
        // 如果 60 秒内发生过强制登录，跳过检查
        if (Number.isFinite(ts) && ts > 0 && Date.now() - ts < 60 * 1000) return true
    } catch {}
    return false
}


// 路由守卫：在每次路由跳转前执行
router.beforeEach(async (to, from, next) => {
    // 设置页面标题
    if (to.meta.title) {
        document.title = to.meta.title
    }

    const store = homeDataStore()
    store.syncAuthFromToken() // 从 Token 同步认证信息

    // 如果访问的是登录页
    if (to.path === '/login') {
        if (!shouldSkipLoginEnsureSession(to)) {
            try {
                // 检查是否存在有效会话
                const session = await store.ensureSession()
                if (session) {
                    // 如果已登录，尝试跳转到默认页面
                    const fallback = await getDefaultAuthedPath(store)
                    if (fallback && fallback !== '/login') {
                        next(fallback)
                        return
                    }
                }
            } catch (e) {}
        }
    }

    // 检查是否是受保护的路由 (以 /user 开头)
    const isProtected = String(to.path || '').startsWith('/user')
    if (isProtected) {
        // 确保会话有效
        const session = await store.ensureSession()
        if (!session) {
            next('/login') // 会话无效，跳转到登录页
            return
        }

        // 获取用户角色和权限信息
        const roleCodes = Array.isArray(store.roleCodes) ? store.roleCodes.map(r => String(r).toLowerCase()) : []
        const isSuper = typeof store?.isSuperAdmin === 'function'
            ? store.isSuperAdmin()
            : Boolean(store.isSuper)
        const userRole = isSuper ? 0 : (roleCodes.includes('yunwei') ? 1 : 2)

        let denied = false
        const hasPermMeta = to.meta.perms && Array.isArray(to.meta.perms) && to.meta.perms.length > 0
        let userPerms = []

        // 检查权限
        if (hasPermMeta) {
            if (!isSuper) {
                const perms = await store.fetchPermissions()
                userPerms = Array.isArray(perms) ? perms.map(String) : []
                const hasAnyPerm = to.meta.perms.some(p => userPerms.includes(String(p)))
                denied = !hasAnyPerm
            }
        } else if (to.meta.roleCodes && Array.isArray(to.meta.roleCodes) && to.meta.roleCodes.length > 0) {
            // 检查角色代码
            if (!isSuper) {
                const allowed = to.meta.roleCodes.some(rc => roleCodes.includes(String(rc).toLowerCase()))
                denied = !allowed
            }
        } else if (to.meta.roles && Array.isArray(to.meta.roles) && to.meta.roles.length > 0) {
            // 检查角色 ID
            denied = !to.meta.roles.includes(userRole)
        }

        // 如果权限不足
        if (denied) {
            ElNotification({
                title: '权限不足',
                message: '您没有权限访问该页面',
                type: 'error',
            })

            // 尝试跳转到其他有权限的页面
            const ctx = { roleCodes, isSuper, userRole, userPerms }
            const fallback = getFirstAccessibleUserPath(ctx)
            if (fallback && fallback !== to.path) {
                next(fallback)
                return
            }
            next('/login')
            return
        }
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
