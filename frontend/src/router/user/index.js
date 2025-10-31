export default [
    {
        path: '/user',
        name: 'user',
        component: () => import('@/components/home/index.vue'),
        children: [
            {
                path: 'home',
                name: 'homeBody',
                component: () => import('@/components/home/home/home.vue'),
                meta: {
                    title: '首页'
                }
            },
            {
                path: 'device',
                name: 'device',
                component: () => import('@/components/DeviceList/index.vue'),
                meta: {
                    title: '设备列表'
                }
            },
        ]
    },
   
]