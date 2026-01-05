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
                meta: { title: '系统概览', roles: [0, 1, 2] }
            },
            {
                path: 'home',
                name: 'home',
                component: home,
                meta: { title: '首页', roles: [0, 1, 2] }
            },
            {
                path: 'device',
                name: 'device',
                component: DeviceList,
                meta: { title: '设备列表', roles: [0, 1] } // 仅管理员和运维可见
            },
            {
                path: 'device/:id',
                name: 'device-detail',
                component: () => import('@/components/DeviceList/DeviceDetail.vue'),
                meta: { title: '设备详情', roles: [0, 1] }
            },
            {
                path: 'ssh/:ip',
                name: 'ssh-connection',
                component: () => import('@/components/SSH/index.vue'),
                meta: {
                    title: 'SSH连接'
                }
            },
            {
                path: 'message',
                name: 'message',
                component: MessageCenter,
                meta: { title: '消息中心', roles: [0, 1, 2] }
            },
            {
                path: 'role',
                name: 'role',
                component: RoleManagement,
                meta: { title: '角色与权限管理', roles: [0] } // 仅管理员可见
            },
            {
                path: 'permission',
                name: 'permission',
                redirect: { name: 'role', query: { tab: 'permission' } },
                meta: { title: '角色与权限管理', roles: [0] } // 仅管理员可见
            },
            {
                path: 'location',
                name: 'location',
                component: Location,
                meta: { title: '位置管理', roles: [0, 1] } // 管理员和运维可见
            },
            {
                path: 'config',
                name: 'config',
                component: GlobalConfig,
                meta: { title: '全局配置', roles: [0] } // 仅管理员可见
            },
            {
                path: 'repair/apply',
                name: 'repair-apply',
                component: RepairApply,
                meta: { title: '故障报修', roles: [0, 1, 2] }
            },
            {
                path: 'repair/list',
                name: 'repair-list',
                component: RepairList,
                meta: { title: '工单列表', roles: [0, 1, 2] }
            },
            {
                path: 'repair/detail/:id',
                name: 'repair-detail',
                component: RepairDetail,
                meta: { title: '工单详情', roles: [0, 1, 2] }
            }
        ]
    }
]

export default homeRoutes
