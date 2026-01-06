import home from '@/components/home/home/home.vue'
import index from '@/components/home/index.vue'
import DeviceList from '@/components/DeviceList/index.vue'
import Dashboard from '@/components/Dashboard/index.vue'
import Organization from '@/components/Organization/index.vue'
import Location from '@/components/Location/index.vue'
import MessageCenter from '@/components/MessageCenter/MessageCenter.vue'
import RoleManagement from '@/components/Role/RoleManagement.vue'
import GlobalConfig from '@/components/System/GlobalConfig.vue'
import RepairApply from '@/components/Repair/Apply.vue'
import RepairList from '@/components/Repair/List.vue'
import RepairDetail from '@/components/Repair/Detail.vue'

const homeRoutes = [
    {
        path: '/user',
        component: index,
        children: [
            {
                path: 'dashboard',
                name: 'dashboard',
                component: Dashboard,
                meta: { title: '系统概览' }
            },
            {
                path: 'home',
                name: 'home',
                component: home,
                meta: { title: '首页' }
            },
            {
                path: 'device',
                name: 'device',
                component: DeviceList,
                meta: { title: '设备列表', perms: ['sys:device:list'] } // 仅管理员和运维可见
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
                component: MessageCenter,
                meta: { title: '消息中心', perms: ['sys:message:access'] }
            },
            {
                path: 'role',
                name: 'role',
                component: RoleManagement,
                meta: { title: '角色与权限管理', roleCodes: ['admin', 'superadmin', 'super_admin'] } // 仅管理员可见
            },
            {
                path: 'permission',
                name: 'permission',
                redirect: { name: 'role', query: { tab: 'permission' } },
                meta: { title: '角色与权限管理', roleCodes: ['admin', 'superadmin', 'super_admin'] } // 仅管理员可见
            },
            {
                path: 'location',
                name: 'location',
                component: Location,
                meta: { title: '位置管理', perms: ['sys:location:view'] } // 管理员和运维可见
            },
            {
                path: 'config',
                name: 'config',
                component: GlobalConfig,
                meta: { title: '全局配置', perms: ['sys:config:view'] } // 仅管理员可见
            },
            {
                path: 'repair/apply',
                name: 'repair-apply',
                component: RepairApply,
                meta: { title: '故障报修', perms: ['sys:repair:create', 'sys:repair:manage'] }
            },
            {
                path: 'repair/list',
                name: 'repair-list',
                component: RepairList,
                meta: { title: '工单列表', perms: ['sys:repair:view', 'sys:repair:handle', 'sys:repair:manage'] }
            },
            {
                path: 'repair/detail/:id',
                name: 'repair-detail',
                component: RepairDetail,
                meta: { title: '工单详情', perms: ['sys:repair:view', 'sys:repair:handle', 'sys:repair:manage'] }
            }
        ]
    }
]

export default homeRoutes
