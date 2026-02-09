const homeRoutes = [
    {
        path: '/user',
        component: () => import('@/components/home/index.vue'),
        children: [
            {
                path: 'dashboard',
                name: 'dashboard',
                component: () => import('@/components/Dashboard/index.vue'),
                meta: { title: '系统概览', perms: ['sys:dashboard:view'] }
            },
            {
                path: 'home',
                name: 'home',
                component: () => import('@/components/home/home/home.vue'),
                meta: { title: '首页' }
            },
            {
                path: 'device',
                name: 'device',
                component: () => import('@/components/DeviceList/index.vue'),
                meta: { title: '设备列表', perms: ['sys:device:list'] } // 仅管理员和运维可见
            },
            {
                path: 'device/recycle',
                name: 'device-recycle',
                component: () => import('@/components/DeviceList/RecycleBin.vue'),
                meta: { title: '回收站', perms: ['sys:device:del'] }
            },
            {
                path: 'device/:id',
                name: 'device-detail',
                component: () => import('@/components/DeviceList/DeviceDetail.vue'),
                meta: { title: '设备详情', perms: ['sys:device:list'] }
            },
            {
                path: 'ssh/:ip',
                name: 'ssh-connection',
                component: () => import('@/components/SSH/index.vue'),
                meta: {
                    title: 'SSH连接',
                    perms: ['sys:ssh:connect']
                }
            },
            {
                path: 'message',
                name: 'message',
                component: () => import('@/components/MessageCenter/MessageCenter.vue'),
                meta: { title: '消息中心', perms: ['sys:message:access'] }
            },
            {
                path: 'message/site/:id',
                name: 'site-message-detail',
                component: () => import('@/components/MessageCenter/SiteMessageDetail.vue'),
                meta: { title: '站内消息', perms: ['sys:message:access'] }
            },
            {
                path: 'message/publish',
                name: 'site-message-publish',
                component: () => import('@/components/MessageCenter/SiteMessagePublish.vue'),
                meta: { title: '发布站内消息', perms: ['sys:message:access'] }
            },
            {
                path: 'role',
                name: 'role',
                component: () => import('@/components/Role/RoleManagement.vue'),
                meta: { title: '角色与权限管理', perms: ['sys:role:manage'] } // 仅管理员和有权限者可见
            },
            {
                path: 'role-distribution',
                name: 'role-distribution',
                component: () => import('@/components/Role/RoleUserDistribution.vue'),
                meta: { title: '角色人员分布', perms: ['sys:role:distribution'] }
            },
            {
                path: 'user-manage',
                name: 'user-manage',
                component: () => import('@/components/System/UserManagement.vue'),
                meta: { title: '用户管理', perms: ['sys:user:view'] }
            },
            {
                path: 'audit',
                name: 'audit',
                component: () => import('@/components/System/UserAdminAudit.vue'),
                meta: { title: '系统操作审计', perms: ['sys:audit:view'] }
            },
            {
                path: 'user-import',
                name: 'user-import',
                component: () => import('@/components/System/UserImport.vue'),
                meta: { title: '批量导入用户', perms: ['sys:user:import'] }
            },
            {
                path: 'permission',
                name: 'permission',
                redirect: { name: 'role', query: { tab: 'permission' } },
                meta: { title: '角色与权限管理', perms: ['sys:role:manage'] } // 仅管理员和有权限者可见
            },
            {
                path: 'location',
                name: 'location',
                component: () => import('@/components/Location/index.vue'),
                meta: { title: '位置管理', perms: ['sys:location:manage', 'sys:location:add', 'sys:location:edit', 'sys:location:del', 'sys:location:bind'] } // 仅管理员和有权限者可见
            },
            {
                path: 'organization',
                name: 'organization',
                component: () => import('@/components/Organization/index.vue'),
                meta: { title: '组织架构', perms: ['sys:org:view'] }
            },
            {
                path: 'config',
                name: 'global-config',
                component: () => import('@/components/System/GlobalConfig.vue'),
                meta: { title: '系统设置', roleCodes: ['admin', 'superadmin'] }
            },
            {
                path: 'config-push',
                name: 'config-push',
                component: () => import('@/components/ConfigPush/index.vue'),
                meta: { title: '配置下发', perms: ['sys:config:push'] }
            },
            {
                path: 'notification-subscribers',
                name: 'notification-subscribers',
                component: () => import('@/components/System/NotificationSubscribers.vue'),
                meta: { title: '预警通知订阅', perms: ['sys:alert:subscribe', 'sys:user:list'] }
            },
            {
                path: 'repair/apply',
                name: 'repair-apply',
                component: () => import('@/components/Repair/Apply.vue'),
                meta: { title: '提交工单' }
            },
            {
                path: 'repair/list',
                name: 'repair-list',
                component: () => import('@/components/Repair/List.vue'),
                meta: { title: '工单列表' }
            },
            {
                path: 'repair/detail/:id',
                name: 'repair-detail',
                component: () => import('@/components/Repair/Detail.vue'),
                meta: { title: '工单详情' }
            }
        ]
    }
]

export default homeRoutes
