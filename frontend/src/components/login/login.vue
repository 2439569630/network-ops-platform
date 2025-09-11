<template>
    <div class="box">
        <transition  :loading="loading" name="fade-transition" mode="out-in">

            <v-card  v-if="isLogin == 0"  class="center" key="login">
                <v-alert-title>
                    登录
                </v-alert-title>
                <v-form v-model="valid" :style="{ marginTop: '20px' }">
                    <v-row>
                        <v-text-field class="form" v-model="userName" label="账号" required type="text" inputmode="numeric" />
                    </v-row>
                    <v-row>
                        <v-text-field class="form" v-model="userPassword" label="密码" type="password" required></v-text-field>
                    </v-row>
                    <v-row>
                        <v-btn color="primary" @click="login(userName, userPassword)">登录</v-btn>
                        <v-btn :style="{ marginLeft: '10px' }" text @click="isLogin = 1">注册</v-btn>
                        <v-btn :style="{ marginLeft: '10px' }" text @click="isLogin = 2">找回密码</v-btn>
                    </v-row>
                </v-form>
            </v-card>
            <v-card v-else-if="isLogin == 1" class="center" key="register">
                <v-alert-title>
                    注册
                </v-alert-title>
                <v-form v-model="registerValid" :style="{ marginTop: '20px' }">
                    <v-row>
                        <v-text-field class="form" v-model="registerUserName" label="账号" required type="text" inputmode="numeric" />
                    </v-row>
                    <v-row>
                        <v-text-field class="form" v-model="registerPassword" label="密码" type="password" required />
                    </v-row>
                    <v-row>
                        <v-text-field class="form" v-model="registerConfirmPassword" label="确认密码" type="password" required />
                    </v-row>
                    <v-row>
                        <v-btn color="primary" @click="Register(registerUserName, registerPassword, registerConfirmPassword)">注册</v-btn>
                        <v-btn :style="{ marginLeft: '10px' }" text @click="isLogin = 0">返回登录</v-btn>
                    </v-row>
                </v-form>
            </v-card>
            <v-card v-else class="center" key="forgot">
                <v-alert-title>
                    找回密码
                </v-alert-title>
                <v-form v-model="forgotValid" :style="{ marginTop: '20px' }">
                    <v-row>
                        <v-text-field class="form" v-model="forgotUserName" label="账号" required type="text" inputmode="numeric" />
                    </v-row>
                    <v-row>
                        <v-text-field class="form" v-model="forgotEmail" label="邮箱" required type="email" />
                    </v-row>
                    <v-row>
                        <v-btn color="primary" @click="ForgotPassword(forgotUserName, forgotEmail)">提交</v-btn>
                        <v-btn :style="{ marginLeft: '10px' }" text @click="isLogin = 0">返回登录</v-btn>
                    </v-row>
                </v-form>
                
            </v-card>
           
        </transition>
    </div>
</template>

<script setup>
import Login from '@/components/login/index.vue'
import { ref } from 'vue'
import router from '@/router'
// 页面切换状态
const isLogin = ref(0) // 0登录 1注册
const userName = ref('')
const userPassword = ref('')

const loading = ref(false)
const login = (userName, userPassword) => {
    loading.value = true
    setTimeout(() => {
        loading.value = false
        router.push('/home')
    }, 2000);



}
</script>
<style scoped>
.box {
    width: 100%;
    height: 100vh;
    background: #f0f2f5;
    /* 隐藏滚动条 */
    overflow: hidden;
    display: flex;
    justify-content: center;
    align-items: center;

}

.center {
    width: 450px;
    padding: 20px;

}

/* css选择器选择第一个form */
form:first-of-type {
    margin-bottom: 20px;
}
</style>