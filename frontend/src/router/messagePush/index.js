import MessagePush from '@/components/MessagePush/MessagePush.vue'

const messagePushRoutes = [
    {
        path: 'message',
        name: 'MessagePush',
        component: MessagePush,
        meta: {
            title: '消息推送'
        },
        children: [
            {
                path: 'serial',
                name: 'SerialPush',
                component: () => import('@/components/MessagePush/SerialPush.vue'), // 假设您会创建这个组件
                meta: {
                    title: '串行推送'
                }
            },
            {
                path: 'parallel',
                name: 'ParallelPush',
                component: () => import('@/components/MessagePush/ParallelPush.vue'), // 假设您会创建这个组件
                meta: {
                    title: '并行推送'
                }
            }
        ]
    }
]

export default messagePushRoutes
