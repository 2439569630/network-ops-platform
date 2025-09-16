

export default [
  {
    path: '/home',
    name: 'home',
    component: () => import('@/components/home/index.vue'),
    children: [
        {
            path: '',
            name: 'homeBody',
            component: () => import('@/components/home/home/home.vue'),
        }
    ]

  },
]