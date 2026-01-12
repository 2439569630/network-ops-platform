export default [
  {
    path: '/login',
    name: 'Login',
    component: () => import('@/components/login/login.vue'),
    meta: { title: '登录' },
  },
  {
    path: '/register',
    name: 'Register',
    component: () => import('@/components/login/register.vue'),
    meta: { title: '注册' },
  },
  {
    path: '/forgot-password',
    name: 'ForgotPassword',
    component: () => import('@/components/login/forgotPassword.vue'),
    meta: { title: '忘记密码' },
  },
]
