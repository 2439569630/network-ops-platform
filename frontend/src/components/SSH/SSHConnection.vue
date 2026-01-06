<template>
  <div class="ssh-container">
    <el-card class="ssh-card">
      <template #header>
        <div class="card-header">
          <div class="header-left">
            <el-icon class="icon"><Monitor /></el-icon>
            <span class="title">SSH 远程连接 - {{ ip }}</span>
          </div>
          <div class="header-actions">
             <el-tag :type="statusType" class="status-tag" effect="dark">{{ statusText }}</el-tag>
             <el-button type="danger" size="small" @click="handleDisconnect" v-if="isConnected">断开连接</el-button>
             <el-button type="primary" size="small" @click="handleConnect" v-else>重新连接</el-button>
             <el-button @click="$router.back()" size="small">返回</el-button>
          </div>
        </div>
      </template>
      
    <div class="terminal-window" ref="terminalRef" @click="focusInput">
        <span class="terminal-content">{{ terminalContent }}</span>
        <input 
            v-if="isConnected"
            v-model="commandInput" 
            @keyup.enter="executeCommand" 
            class="terminal-input" 
            ref="inputRef"
            autocomplete="off"
            spellcheck="false"
        />
    </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Monitor } from '@element-plus/icons-vue';
import Cookies from 'js-cookie'; // 引入 js-cookie
import axios from '@/axios/axios';

const route = useRoute();
const router = useRouter();
const ip = ref(route.params.ip || 'Unknown');

const isConnected = ref(false);
const terminalContent = ref('');
const commandInput = ref('');
const inputRef = ref(null);
const terminalRef = ref(null);
let ws = null;
let reconnectTimer = null;
let reconnectAttempted = false;

const statusType = computed(() => isConnected.value ? 'success' : 'info');
const statusText = computed(() => isConnected.value ? '已连接' : '未连接');

const handleConnect = (options = {}) => {
    if (ws) {
        ws.__manualClose = true;
        ws.close();
    }
    terminalContent.value = '';
    
    // 获取 Token
    const token = Cookies.get('token');
    
    if (!token) {
        terminalContent.value = '错误：未登录或 Token 无效。\n';
        return;
    }

    // 动态获取 WebSocket 地址
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = window.location.hostname;
    const port = window.location.port === '5173' ? '8000' : window.location.port;
    const wsPort = port ? `:${port}` : '';

    // 将 token 作为 query 参数传递
    const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/ws/ssh/${ip.value}?token=${token}`;
    
    console.log('Connecting to SSH WebSocket:', wsUrl);

    try {
        ws = new WebSocket(wsUrl);
        ws.__manualClose = false;
        
        ws.onopen = () => {
            isConnected.value = true;
            reconnectAttempted = false;
            // terminalContent.value += "连接成功。\n";
            focusInput();
        };
        
        ws.onmessage = (event) => {
            // 检查是否包含清屏指令 (简单的检查，实际可能需要更复杂的 ANSI 解析)
            if (event.data.includes('\x1b[2J') || event.data.includes('\x1b[H')) {
                 // 清屏：只保留最后收到的非控制字符内容，或者完全清空
                 // 这里简单处理：如果包含清屏指令，就清空当前内容，然后追加剩余内容
                 // 注意：event.data 可能包含 "清屏指令 + 新的提示符"
                 // 简单的处理方式：
                 const parts = event.data.split(/(\x1b\[2J\x1b\[H|\x1b\[H\x1b\[2J|\x1b\[2J|\x1b\[H)/);
                 // 如果最后一个部分是有效的文本，则只显示它。
                 // 更好的做法是清空 terminalContent，然后追加过滤掉控制字符后的内容
                 terminalContent.value = parts[parts.length - 1];
            } else {
                terminalContent.value += event.data;
            }
            
            nextTick(() => {
                scrollToBottom();
            });
        };
        
        ws.onclose = (e) => {
            isConnected.value = false;
            if (ws?.__manualClose) return;

            terminalContent.value += `\n连接已断开 (Code: ${e.code}).\n`;
            scrollToBottom();

            const closeCode = Number(e?.code || 0);
            if (closeCode === 4003) return;
            if (closeCode !== 4001) return;
            if (reconnectAttempted) return;

            reconnectAttempted = true;
            if (reconnectTimer) clearTimeout(reconnectTimer);
            reconnectTimer = setTimeout(async () => {
                try {
                    const res = await axios.post('/api/v1/auth/refresh');
                    const nextToken = res?.data?.token;
                    if (nextToken) Cookies.set('token', nextToken, { sameSite: 'lax' });
                    handleConnect({ reason: 'auth_refresh' });
                } catch (err) {
                    terminalContent.value += '\n认证已失效，请重新登录。\n';
                    scrollToBottom();
                }
            }, 500);
        };
        
        ws.onerror = (error) => {
            console.error("WebSocket error:", error);
            terminalContent.value += "\n连接发生错误。\n";
            isConnected.value = false;
        };
    } catch (e) {
        console.error("WebSocket creation failed:", e);
        terminalContent.value += `\n连接创建失败: ${e.message}\n`;
    }
};

const handleDisconnect = () => {
    if (ws) {
        ws.close();
    }
};

const executeCommand = () => {
    if (!ws || !isConnected.value) return;
    
    const cmd = commandInput.value;
    // Send command via WebSocket
    ws.send(cmd);
    
    commandInput.value = '';
    // Note: We don't manually append cmd to terminalContent because the server (shell) should echo it back.
};

const focusInput = () => {
    if (inputRef.value && isConnected.value) {
        inputRef.value.focus();
    }
};

const scrollToBottom = () => {
    if (terminalRef.value) {
        terminalRef.value.scrollTop = terminalRef.value.scrollHeight;
    }
};

onMounted(() => {
    handleConnect();
});

onBeforeUnmount(() => {
    if (ws) {
        ws.__manualClose = true;
        ws.close();
    }
    if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
    }
});
</script>

<style scoped>
.ssh-container {
    padding: 20px;
    height: 100%;
    box-sizing: border-box;
    display: flex;
    flex-direction: column;
}

.ssh-card {
    flex: 1;
    display: flex;
    flex-direction: column;
    border-radius: 12px;
}

:deep(.el-card__body) {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 0;
    overflow: hidden;
}

.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 10px;
}

.title {
    font-weight: bold;
    font-size: 16px;
}

.header-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}

.terminal-window {
    background-color: #1e1e1e;
    color: #f0f0f0;
    font-family: 'Consolas', 'Monaco', 'Courier New', monospace;
    padding: 15px;
    flex: 1;
    overflow-y: auto;
    font-size: 14px;
    line-height: 1.5;
    cursor: text;
    display: block; /* 改为 block，让 span 和 input 流式排列 */
}

.terminal-content {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;
}

.input-line {
    display: inline; /* 不再需要这个容器，或者改为 inline */
}

.terminal-input {
    background: transparent;
    border: none;
    color: #f0f0f0;
    font-family: inherit;
    font-size: inherit;
    outline: none;
    padding: 0;
    margin: 0;
    caret-color: #00ff00;
    width: 50%; /* 给输入框一定宽度，或者自适应 */
    min-width: 10px;
    display: inline-block;
    vertical-align: bottom; /* 对齐底部 */
}
</style>
