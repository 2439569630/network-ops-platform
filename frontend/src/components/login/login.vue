<template>
    <div class="login-box">
        <div class="login-left">
            <h1>网络设备自动化运维平台</h1>
        </div>
        <transition  :loading="loading" :style="{color: 'white'}" name="fade-transition" mode="out-in">

            <v-card  v-if="isLogin == 0"  class="login-center" key="login">
                <v-alert-title >
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
                        <v-btn  :style="{  background: '#4caf50'}" @click="login(userName, userPassword)">登录</v-btn>
                        <v-btn :style="{ marginLeft: '10px', background: 'blue' }" text @click="isLogin = 1">注册</v-btn>
                        <v-btn :style="{ marginLeft: '10px', background: 'none' }" text @click="isLogin = 2">找回密码</v-btn>
                    </v-row>
                </v-form>
            </v-card>
            <v-card v-else-if="isLogin == 1" class="login-center" key="register">
                <v-alert-title>
                    注册
                </v-alert-title>
                <v-form :style="{ marginTop: '20px' }">
                    <v-row>
                        <v-text-field class="login-form" v-model="registerUserName" label="账号" required type="text" inputmode="numeric" />
                    </v-row>
                    <v-row>
                        <v-text-field class="login-form" v-model="registerPassword" label="密码" type="password" required />
                    </v-row>
                    <v-row>
                        <v-text-field class="login-form" v-model="registerConfirmPassword" label="确认密码" type="password" required />
                    </v-row>
                    <v-row>
                        <v-btn :style="{  background: 'blue' }"  @click="Register(registerUserName, registerPassword, registerConfirmPassword)">注册</v-btn>
                        <v-btn :style="{ marginLeft: '10px',  background: 'none' }" text @click="isLogin = 0">返回登录</v-btn>
                    </v-row>
                </v-form>
            </v-card>
            <v-card v-else class="login-center" key="forgot">
                <v-alert-title>
                    找回密码
                </v-alert-title>
                <v-form  :style="{ marginTop: '20px' }">
                    <v-row>
                        <v-text-field class="login-form" v-model="forgotUserName" label="账号" required type="text" inputmode="numeric" />
                    </v-row>
                    <v-row>
                        <v-text-field class="login-form" v-model="forgotEmail" label="邮箱" required type="email" />
                    </v-row>
                    <v-row>
                        <v-btn :style="{background: '#4caf50'}" @click="ForgotPassword(forgotUserName, forgotEmail)">提交</v-btn>
                        <v-btn :style="{ marginLeft: '10px' ,  background: 'none' }" text @click="isLogin = 0">返回登录</v-btn>
                    </v-row>
                </v-form>
                
            </v-card>
           
        </transition>
    </div>
</template>

<script setup>
import Login from '@/components/login/index.vue'
import { ref, onMounted } from 'vue'
import router from '@/router'
import axios from 'axios'
import { ElNotification } from 'element-plus'


// 页面切换状态
const isLogin = ref(0) // 0登录 1注册
const userName = ref('')
const userPassword = ref('')

// 记住密码
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





const loading = ref(false)
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

    axios.post('/login', {
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
        await router.push('/user/home')

        ElNotification({
            title: 'Success',
            message: res.data.message || '登录成功',
            type: 'success',
        })
        
        
        
    }).catch(err => {
        console.log(err)
        
        ElNotification({
            title: 'Error',
            message: err.response.data.message || '登录失败',
            type: 'error',
        })
    })


}
</script>
<style scoped>
.login-box {
    width: 100%;
    height: 80vh;
    /* background: #f0f2f5; */
    
    /* 隐藏滚动条 */
    overflow: hidden;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    

}

.login-center {
    width: 450px;
    padding: 20px;
    background: rgba(45, 55, 72, 0.6);
    border-radius: 10px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    
}

/* css选择器选择第一个form */
login-form:first-of-type {
    margin-bottom: 20px;
    
}


.login-left { 
    width: auto;
    height: 20%;
    display: flex;
    align-items: center;
    color: var(--text);
    font-size: 1.2rem;
    font-weight: 700;
}
h1 {
    font-size: 2.5rem;
    font-weight: 700;
    color: var(--text);
    /* 过渡 */
    transition: all 0.3s ease-in-out;
}

h1:hover {
    transform: translateY(-10px) scale(1.1);
    color: var(--accent);
}
</style>