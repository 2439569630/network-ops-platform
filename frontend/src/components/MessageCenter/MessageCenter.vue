<template>
  <div class="message-center">
    <el-card>
      <template #header>
        <div class="card-header">
          <span>消息中心</span>
        </div>
      </template>

      <el-tabs v-model="activeTab">
        <!-- 告警监控 (Trap) -->
        <el-tab-pane label="实时告警" name="alerts">
             <div class="alert-toolbar">
                <el-button type="primary" size="small" @click="clearAlerts">清空告警</el-button>
             </div>
             <el-table :data="alerts" style="width: 100%" row-key="id" stripe>
                <el-table-column prop="time" label="时间" width="180" />
                <el-table-column prop="level" label="级别" width="100">
                    <template #default="scope">
                        <el-tag :type="getAlertLevelType(scope.row.level)">{{ scope.row.level }}</el-tag>
                    </template>
                </el-table-column>
                <el-table-column prop="source" label="来源 IP" width="150" />
                <el-table-column prop="type" label="类型" width="150" />
                <el-table-column prop="description" label="描述" />
             </el-table>
             <el-empty v-if="alerts.length === 0" description="暂无实时告警" />
        </el-tab-pane>

        <!-- 消息通知列表 -->
        <el-tab-pane label="设备通知" name="notifications">
            <el-table :data="notifications" style="width: 100%" v-loading="loading">
                <el-table-column prop="created_at" label="时间" width="180">
                    <template #default="scope">
                        {{ new Date(scope.row.created_at).toLocaleString() }}
                    </template>
                </el-table-column>
                <el-table-column prop="level" label="级别" width="100">
                    <template #default="scope">
                        <el-tag :type="getLevelType(scope.row.level)">{{ scope.row.level }}</el-tag>
                    </template>
                </el-table-column>
                <el-table-column prop="device_name" label="设备" width="150" />
                <el-table-column prop="message" label="内容" />
            </el-table>
            <div class="pagination-container" v-if="notifications.length > 0">
                 <!-- 简易分页，实际应配合后端分页 -->
                 <el-pagination layout="prev, pager, next" :total="100" />
            </div>
             <el-empty v-if="notifications.length === 0 && !loading" description="暂无通知" />
        </el-tab-pane>

        <!-- 消息设置 -->
        <el-tab-pane label="推送设置" name="settings">
            <div class="settings-container" v-loading="configLoading">
                <el-form label-position="left" label-width="150px">
                    <el-divider content-position="left">邮箱通知</el-divider>
                    <el-form-item label="开启邮箱通知">
                        <el-switch v-model="config.enable_email" />
                    </el-form-item>
                    
                    <template v-if="config.enable_email">
                         <el-form-item label="使用全局配置" v-if="canUseGlobal">
                            <el-switch v-model="config.use_global_email" />
                            <div class="hint">开启后将使用系统统一配置的邮件服务器发送通知（需权限）</div>
                        </el-form-item>
                        
                        <div v-if="!config.use_global_email" class="sub-config">
                             <el-form-item label="SMTP服务器">
                                <el-input v-model="config.email_config.host" placeholder="smtp.example.com" />
                             </el-form-item>
                             <el-form-item label="端口">
                                <el-input v-model="config.email_config.port" placeholder="465" />
                             </el-form-item>
                             <el-form-item label="用户名">
                                <el-input v-model="config.email_config.username" placeholder="user@example.com" />
                             </el-form-item>
                             <el-form-item label="授权码/密码">
                                <el-input v-model="config.email_config.password" type="password" show-password />
                             </el-form-item>
                        </div>
                        <el-form-item label="测试接收邮箱">
                            <div class="test-row">
                                <el-input v-model="testEmailTarget" placeholder="输入邮箱地址" style="width: 200px" />
                                <el-button type="info" size="small" @click="handleTest('email')">发送测试邮件</el-button>
                            </div>
                        </el-form-item>
                    </template>

                    <el-divider content-position="left">PushPlus 推送</el-divider>
                    <el-form-item label="开启PushPlus">
                        <el-switch v-model="config.enable_pushplus" />
                    </el-form-item>
                    <el-form-item label="Token" v-if="config.enable_pushplus">
                        <div class="test-row">
                             <el-input v-model="config.pushplus_token" placeholder="PushPlus Token" />
                             <el-button type="info" size="small" @click="handleTest('pushplus')">测试</el-button>
                        </div>
                    </el-form-item>

                    <el-divider content-position="left">HTTP 回调</el-divider>
                    <el-form-item label="开启HTTP回调">
                        <el-switch v-model="config.enable_http" />
                    </el-form-item>
                    <el-form-item label="Webhook URL" v-if="config.enable_http">
                        <div class="test-row">
                            <el-input v-model="config.http_url" placeholder="http://your-api.com/callback" />
                            <el-button type="info" size="small" @click="handleTest('http')">测试</el-button>
                        </div>
                    </el-form-item>

                    <el-form-item>
                        <el-button type="primary" @click="saveConfig">保存配置</el-button>
                    </el-form-item>
                </el-form>
            </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted, reactive } from 'vue';
import axios from '@/axios/axios';
import { ElMessage } from 'element-plus';
import { jwtDecode } from 'jwt-decode';
import Cookies from 'js-cookie';

const activeTab = ref('alerts'); // 默认显示告警
const notifications = ref([]);
const alerts = ref([]); // 实时告警列表
const loading = ref(false);
const configLoading = ref(false);
const canUseGlobal = ref(false);
const testEmailTarget = ref('');
let ws = null; // WebSocket 实例

const getAlertLevelType = (level) => {
    switch(level) {
        case 'error': return 'danger';
        case 'warning': return 'warning';
        case 'success': return 'success';
        default: return 'info';
    }
};

const clearAlerts = () => {
    alerts.value = [];
};

// 连接 WebSocket 接收实时告警
const initAlertWebSocket = () => {
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = window.location.hostname
    const port = window.location.port === '5173' ? '8000' : window.location.port
    const wsPort = port ? `:${port}` : ''
    const token = Cookies.get('token')
    
    // 复用已有的 WS 接口，或者新建一个专门的 Alert WS
    // 这里假设后端 notification 模块提供了一个 /ws/alerts
    // 暂时如果没有，我们可以复用 device list 的 ws，或者在 notification.py 里加一个
    // 为了简单，我们复用设备列表的 WS 通道，或者新建一个
    // 由于后端 notification 还没有 WS，我们先用轮询模拟或者假设后端有 (需补充)
    
    // 补充：后端 Routers/User/notification.py 需要增加 WS 接口
    const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/notifications/ws/alerts?token=${token}`
    
    try {
        ws = new WebSocket(wsUrl);
        ws.onopen = () => {
            console.log('Alert WebSocket connected');
        };
        ws.onmessage = (event) => {
            try {
                const alert = JSON.parse(event.data);
                alerts.value.unshift(alert);
                // 最多保留 50 条
                if (alerts.value.length > 50) {
                    alerts.value.pop();
                }
            } catch (e) {
                console.error('Alert WS parse error:', e);
            }
        };
        ws.onclose = () => {
            console.log('Alert WebSocket closed');
        };
    } catch (e) {
        console.error('Alert WS error:', e);
    }
}

const config = reactive({
    enable_email: false,
    use_global_email: false,
    email_config: {
        host: '',
        port: '',
        username: '',
        password: ''
    },
    enable_pushplus: false,
    pushplus_token: '',
    enable_http: false,
    http_url: ''
});

const getLevelType = (level) => {
    switch(level) {
        case 'error': return 'danger';
        case 'warning': return 'warning';
        case 'info': return 'info';
        default: return '';
    }
};

const fetchNotifications = async () => {
    loading.value = true;
    try {
        const res = await axios.get('/api/v1/notifications/history');
        if (res.data.code === 200) {
            notifications.value = res.data.data;
        }
    } catch (error) {
        ElMessage.error('获取通知失败');
    } finally {
        loading.value = false;
    }
};

const fetchConfig = async () => {
    configLoading.value = true;
    try {
        const res = await axios.get('/api/v1/notifications/config');
        if (res.data.code === 200) {
            const data = res.data.data;
            
            // 确保 email_config 结构完整，防止 v-model 报错
            if (!data.email_config) {
                data.email_config = {};
            }
            // 合并默认值
            data.email_config = {
                host: '',
                port: '',
                username: '',
                password: '',
                ...data.email_config
            };

            Object.assign(config, data);
        }
    } catch (error) {
        ElMessage.error('获取配置失败');
    } finally {
        configLoading.value = false;
    }
};

const saveConfig = async () => {
    try {
        const res = await axios.post('/api/v1/notifications/config', config);
        if (res.data.code === 200) {
            ElMessage.success('配置保存成功');
        } else {
            ElMessage.error(res.data.message || '保存失败');
        }
    } catch (error) {
        ElMessage.error('保存失败: ' + (error.response?.data?.detail?.message || error.message));
    }
};

const handleTest = async (channel) => {
    try {
        const payload = {
            channel: channel,
            config: config,
            target: channel === 'email' ? testEmailTarget.value : null
        };
        
        const res = await axios.post('/api/v1/notifications/test', payload);
        if (res.data.code === 200) {
            ElMessage.success('测试消息发送成功');
        } else {
            ElMessage.error(res.data.message || '测试失败');
        }
    } catch (error) {
        ElMessage.error('测试请求失败: ' + (error.response?.data?.detail?.message || error.message));
    }
};

onMounted(() => {
    const token = Cookies.get('token');
    if (token) {
        try {
            const decoded = jwtDecode(token);
            // 权限等级 <= 1 可以使用全局配置
            canUseGlobal.value = Number(decoded.permission_level) <= 1;
        } catch (e) {}
    }

    fetchNotifications();
    fetchConfig();
    initAlertWebSocket(); // 启动 WS
});

onUnmounted(() => {
    if (ws) {
        ws.close();
    }
});
</script>

<style scoped>
.message-center {
    padding: 20px;
}
.settings-container {
    max-width: 600px;
    padding: 20px 0;
}
.sub-config {
    margin-left: 20px;
    padding: 15px;
    background: #f8f9fa;
    border-radius: 4px;
    margin-bottom: 20px;
}
.hint {
    font-size: 12px;
    color: #909399;
    margin-top: 5px;
}
.test-row {
    display: flex;
    gap: 10px;
    align-items: center;
    width: 100%;
}
.pagination-container {
    margin-top: 20px;
    display: flex;
    justify-content: flex-end;
}
</style>
