import { createRouter, createWebHistory } from 'vue-router'
import loginRoutes from '@/router/login/index.js'
import homeRoutes from '@/router/user/index.js'
import { ElNotification } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'

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

const joinPaths = (base, child) => {
    const b = String(base || '').replace(/\/+$/, '')
    const c = String(child || '').replace(/^\/+/, '')
    return `${b}/${c}`
}

const flattenUserRouteCandidates = () => {
    const out = []
    const visit = (routes, basePath = '') => {
        (routes || []).forEach(r => {
            const path = r?.path
            if (typeof path !== 'string') return
            const fullPath = path.startsWith('/') ? path : joinPaths(basePath, path)
            if (fullPath.includes(':') || fullPath.includes('*')) {
                if (Array.isArray(r.children) && r.children.length > 0) {
                    visit(r.children, fullPath)
                }
                return
            }
            if (fullPath.startsWith('/user') && fullPath !== '/user') {
                out.push({ path: fullPath, meta: r.meta || {} })
            }
            if (Array.isArray(r.children) && r.children.length > 0) {
                visit(r.children, fullPath)
            }
        })
    }
    visit(homeRoutes, '')
    const uniq = []
    const seen = new Set()
    out.forEach(r => {
        if (!seen.has(r.path)) {
            seen.add(r.path)
            uniq.push(r)
        }
    })
    const prioritize = ['/user/dashboard', '/user/home', '/user/message']
    uniq.sort((a, b) => {
        const ia = prioritize.indexOf(a.path)
        const ib = prioritize.indexOf(b.path)
        if (ia !== -1 || ib !== -1) return (ia === -1 ? 999 : ia) - (ib === -1 ? 999 : ib)
        return 0
    })
    return uniq
}

const userRouteCandidates = flattenUserRouteCandidates()

const canAccessRouteMeta = (meta, ctx) => {
    const m = meta || {}
    if (m.perms && Array.isArray(m.perms) && m.perms.length > 0) {
        if (ctx.isSuper) return true
        return m.perms.some(p => ctx.userPerms.includes(String(p)))
    }
    if (m.roleCodes && Array.isArray(m.roleCodes) && m.roleCodes.length > 0) {
        if (ctx.isSuper) return true
        return m.roleCodes.some(rc => ctx.roleCodes.includes(String(rc).toLowerCase()))
    }
    if (m.roles && Array.isArray(m.roles) && m.roles.length > 0) {
        return m.roles.includes(ctx.userRole)
    }
    return true
}

const getFirstAccessibleUserPath = (ctx) => {
    for (const r of userRouteCandidates) {
        if (canAccessRouteMeta(r.meta, ctx)) return r.path
    }
    return '/login'
}

const getDefaultAuthedPath = async (store) => {
    const roleCodes = Array.isArray(store?.roleCodes) ? store.roleCodes.map(r => String(r).toLowerCase()) : []
    const isSuper = Boolean(store?.isSuper)
    const userRole = isSuper ? 0 : (roleCodes.includes('yunwei') ? 1 : 2)
    const perms = isSuper ? [] : await store.fetchPermissions()
    const ctx = { roleCodes, isSuper, userRole, userPerms: Array.isArray(perms) ? perms.map(String) : [] }
    return getFirstAccessibleUserPath(ctx)
}

const shouldSkipLoginEnsureSession = (to) => {
    const reason = String(to?.query?.reason || '').trim()
    if (reason) return true
    try {
        const ts = Number(sessionStorage.getItem('auth:force_login_at') || 0)
        if (Number.isFinite(ts) && ts > 0 && Date.now() - ts < 60 * 1000) return true
    } catch {}
    return false
}


// 路由守卫
router.beforeEach(async (to, from, next) => {
    // 设置页面标题
    if (to.meta.title) {
        document.title = to.meta.title
    }

    const store = homeDataStore()
    store.syncAuthFromToken()

    if (to.path === '/login') {
        if (!shouldSkipLoginEnsureSession(to)) {
            try {
                const session = await store.ensureSession()
                if (session) {
                    const fallback = await getDefaultAuthedPath(store)
                    if (fallback && fallback !== '/login') {
                        next(fallback)
                        return
                    }
                }
            } catch (e) {}
        }
    }

    const isProtected = String(to.path || '').startsWith('/user')
    if (isProtected) {
        const session = await store.ensureSession()
        if (!session) {
            next('/login')
            return
        }

        const roleCodes = Array.isArray(store.roleCodes) ? store.roleCodes.map(r => String(r).toLowerCase()) : []
        const isSuper = Boolean(store.isSuper)
        const userRole = isSuper ? 0 : (roleCodes.includes('yunwei') ? 1 : 2)

        let denied = false
        const hasPermMeta = to.meta.perms && Array.isArray(to.meta.perms) && to.meta.perms.length > 0
        let userPerms = []

        if (hasPermMeta) {
            if (!isSuper) {
                const perms = await store.fetchPermissions()
                userPerms = Array.isArray(perms) ? perms.map(String) : []
                const hasAnyPerm = to.meta.perms.some(p => userPerms.includes(String(p)))
                denied = !hasAnyPerm
            }
        } else if (to.meta.roleCodes && Array.isArray(to.meta.roleCodes) && to.meta.roleCodes.length > 0) {
            if (!isSuper) {
                const allowed = to.meta.roleCodes.some(rc => roleCodes.includes(String(rc).toLowerCase()))
                denied = !allowed
            }
        } else if (to.meta.roles && Array.isArray(to.meta.roles) && to.meta.roles.length > 0) {
            denied = !to.meta.roles.includes(userRole)
        }

        if (denied) {
            ElNotification({
                title: '权限不足',
                message: '您没有权限访问该页面',
                type: 'error',
            })

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
