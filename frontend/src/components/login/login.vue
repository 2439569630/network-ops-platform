<template>
    <!-- 登录页面容器 -->
    <div class="login-box">
        <!-- 左侧标题区域 -->
        <div class="login-left">
            <h1>网络设备自动化运维平台</h1>
        </div>
        <v-card class="login-center">
            <v-alert-title>
                登录
            </v-alert-title>
            <v-form :style="{ marginTop: '20px' }">
                <v-row>
                    <v-text-field class="login-form" v-model="userName" label="账号" required type="text" inputmode="numeric" />
                </v-row>
                <v-row>
                    <v-text-field class="login-form" v-model="userPassword" label="密码" type="password" required></v-text-field>
                </v-row>
                <v-row>
                    <v-checkbox v-model="rememberPassword" label="记住密码"></v-checkbox>
                </v-row>
                <v-row>
                    <v-btn :style="{ background: '#4caf50' }" @click="login(userName, userPassword)">登录</v-btn>
                </v-row>
            </v-form>
        </v-card>
    </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import router from '@/router'
import axios from '@/axios/axios'
import Cookies from 'js-cookie'
import { ElNotification } from 'element-plus'


const userName = ref('') // 登录用户名
const userPassword = ref('') // 登录密码

// 记住密码功能
const rememberPassword = ref(false)

// 生命周期-组件挂载时
onMounted(() => {
    // 如果localStorage中有账号密码，则自动填充
    if (localStorage.getItem('username') && localStorage.getItem('password')) {
        userName.value = localStorage.getItem('username')
        userPassword.value = localStorage.getItem('password')
        rememberPassword.value = true
    }
})


const login = async (userName, userPassword) => {
    // not null
    if (userName == '' || userPassword == '') {
        ElNotification({
            title: 'Error',
            message: '账号或密码不能为空',
            type: 'error',
        })
        return
    }

    axios.post('/api/v1/auth/login', {
        username: userName,
        password: userPassword
    }).then(async res => {
        if (rememberPassword.value) {
            localStorage.setItem('username', userName)
            localStorage.setItem('password', userPassword)
        } else {
            localStorage.removeItem('username')
            localStorage.removeItem('password')
        }
        
        if (res.data.token) {
            Cookies.set('token', res.data.token, { sameSite: 'lax' })
        }

        await router.push('/user/dashboard')

        ElNotification({
            title: 'Success',
            message: res.data.message || '登录成功',
            type: 'success',
        })
        
        
        
    }).catch(err => {
        console.log(err)
        
        ElNotification({
            title: 'Error',
            message: err.response?.data?.message || err.message || '登录失败',
            type: 'error',
        })
    })


}
</script>
<style scoped>
/* 登录框整体布局样式 */
.login-box {
    width: 100%;
    height: 100vh;
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
}

/* 登录中心区域样式 */
.login-center {
    width: 450px;
    padding: 30px;
    background: rgba(255, 255, 255, 0.95);
    backdrop-filter: blur(15px);
    border-radius: 20px;
    box-shadow: 0 15px 35px rgba(0, 0, 0, 0.2);
    border: 1px solid rgba(255, 255, 255, 0.3);
    z-index: 1;
}

/* 登录标题区域样式 */
.login-left { 
    width: auto;
    height: 20%;
    display: flex;
    align-items: center;
    color: var(--text);
    font-size: 1.2rem;
    font-weight: 700;
    margin-bottom: 20px;
}

/* 主标题样式 */
h1 {
    font-size: 2.5rem;
    font-weight: 700;
    color: white;
    text-shadow: 0 2px 10px rgba(0, 0, 0, 0.3);
    transition: all 0.3s ease-in-out;
    position: relative;
    z-index: 1;
}

/* 主标题悬停效果 */
h1:hover {
    transform: translateY(-5px);
    text-shadow: 0 4px 15px rgba(0, 0, 0, 0.4);
}

/* 表单标题样式 */
.v-alert-title {
    font-size: 1.8rem;
    font-weight: 600;
    color: #333;
    text-align: center;
    margin-bottom: 10px;
    padding-bottom: 15px;
    border-bottom: 2px solid #f0f0f0;
}

/* 输入框样式优化 */
.v-text-field {
    margin-bottom: 20px;
}

/* 输入框内部样式 */
.v-text-field :deep(.v-field) {
    background-color: rgba(255, 255, 255, 0.8);
    border-radius: 10px;
    border: 2px solid #e0e0e0;
    transition: all 0.3s ease;
}

/* 输入框悬停效果 */
.v-text-field :deep(.v-field):hover {
    border-color: #a8a8a8;
    box-shadow: 0 0 0 2px rgba(102, 126, 234, 0.1);
}

/* 输入框聚焦效果 */
.v-text-field :deep(.v-field--focused) {
    border-color: #667eea;
    box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.2);
}

/* 输入框标签样式 */
.v-text-field :deep(.v-label) {
    color: #666;
    font-weight: 500;
}

/* 输入框聚焦时标签样式 */
.v-text-field :deep(.v-field--focused .v-label) {
    color: #667eea;
}

/* 输入框文本样式 */
.v-text-field :deep(input) {
    color: #333;
    font-size: 1rem;
}

/* 复选框样式 */
.v-checkbox :deep(.v-selection-control) {
    margin-top: 10px;
    color: #666;

}

/* 复选框标签样式 */
.v-checkbox :deep(.v-label) {
    color: #666;
    font-size: 0.9rem;
}

/* 按钮样式优化 */
.v-btn {
    border-radius: 10px;
    font-weight: 600;
    text-transform: none;
    letter-spacing: 0.5px;
    transition: all 0.3s ease;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    height: 45px;
    padding: 0 25px;
    margin-right: 10px;
    margin-bottom: 10px;
}

.v-btn:first-of-type {
    background: linear-gradient(135deg, #4caf50, #45a049);
    color: white;
    border: none;
}

.v-btn:first-of-type:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 12px rgba(76, 175, 80, 0.3);
    background: linear-gradient(135deg, #45a049, #3d8b40);
}

.v-btn:nth-of-type(2) {
    background: linear-gradient(135deg, #2196F3, #0b7dda);
    color: white;
    border: none;
}

.v-btn:nth-of-type(2):hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 12px rgba(33, 150, 243, 0.3);
    background: linear-gradient(135deg, #0b7dda, #0a6ebe);
}

.v-btn:last-of-type {
    background: transparent;
    color: #667eea;
    border: 2px solid #667eea;
}

.v-btn:last-of-type:hover {
    background: rgba(102, 126, 234, 0.1);
    transform: translateY(-2px);
    box-shadow: 0 4px 8px rgba(102, 126, 234, 0.2);
}

/* 过渡动画优化 */
.fade-transition-enter-active,
.fade-transition-leave-active {
    transition: all 0.4s cubic-bezier(0.55, 0, 0.1, 1);
}

.fade-transition-enter-from {
    opacity: 0;
    transform: translateX(30px);
}

.fade-transition-leave-to {
    opacity: 0;
    transform: translateX(-30px);
}

/* 响应式设计 */
@media (max-width: 600px) {
    .login-center {
        width: 90%;
        padding: 20px;
    }
    
    h1 {
        font-size: 2rem;
    }
    
    .v-alert-title {
        font-size: 1.5rem;
    }
}

/* 添加一些装饰元素 */
.login-box::before {
    content: '';
    position: absolute;
    width: 200px;
    height: 200px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.1);
    top: 10%;
    left: 10%;
    animation: float 6s ease-in-out infinite;
}

.login-box::after {
    content: '';
    position: absolute;
    width: 150px;
    height: 150px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.05);
    bottom: 10%;
    right: 10%;
    animation: float 8s ease-in-out infinite reverse;
}



@keyframes float {
    0%, 100% {
        transform: translateY(0) rotate(0deg);
    }
    50% {
        transform: translateY(-20px) rotate(180deg);
    }
}
</style>
