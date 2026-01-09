<template>
  <div class="device-detail-container">
    <!-- 顶部导航栏 -->
    <el-card class="page-header-card" shadow="never">
      <template #header>
        <div class="page-header">
          <div class="header-left">
            <el-button type="default" :icon="ArrowLeft" @click="goBack">返回列表</el-button>
            <div class="device-title">
              <span class="device-name">{{ deviceData.name }}</span>
              <el-tag effect="plain" type="info" class="device-ip">{{ deviceData.ip }}</el-tag>
              <el-tag :type="deviceData.status === 'online' ? 'success' : 'danger'" effect="dark">
                {{ deviceData.status === 'online' ? '在线' : '离线' }}
              </el-tag>
            </div>
          </div>
          <div class="header-right">
            <el-button v-if="canSsh" type="primary" :icon="Monitor" @click="handleWebSSH">WebSSH 连接</el-button>
            <el-button :icon="Refresh" @click="fetchDeviceData" :loading="loading">刷新数据</el-button>
            <el-button type="danger" plain :icon="SwitchButton" @click="handleRestart">重启设备</el-button>
          </div>
        </div>
      </template>
    </el-card>

    <div class="main-content">
      <el-row :gutter="20">
        <!-- 左侧栏：基础信息与状态 -->
        <el-col :span="8">
          <div class="left-column">
            <!-- 基础概览卡片 -->
            <el-card class="info-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span><el-icon><InfoFilled /></el-icon> 基础概览</span>
                </div>
              </template>
              <el-descriptions :column="1" border>
                <el-descriptions-item label="类型">{{ deviceData.type }}</el-descriptions-item>
                <el-descriptions-item label="厂商">{{ deviceData.vendor }}</el-descriptions-item>
                <el-descriptions-item label="型号">{{ deviceData.model }}</el-descriptions-item>
                <el-descriptions-item label="序列号">{{ deviceData.serialNumber }}</el-descriptions-item>
                <el-descriptions-item label="位置">{{ deviceData.location }}</el-descriptions-item>
                
                <!-- 网络设备特有字段 -->
                <el-descriptions-item v-if="isNetworkDevice" label="SNMP 版本">{{ deviceData.snmpVersion }}</el-descriptions-item>
                
                <!-- 服务器/Linux特有字段 -->
                <el-descriptions-item v-if="!isNetworkDevice" label="内核版本">{{ deviceData.osVersion }}</el-descriptions-item>
              </el-descriptions>
            </el-card>

            <!-- 实时健康度卡片 -->
            <el-card class="health-card" shadow="hover">
              <template #header>
                <div class="card-header">
                  <span><el-icon><Odometer /></el-icon> 实时健康度</span>
                </div>
              </template>
              <div class="health-metrics">
                <div class="metric-item">
                  <span class="metric-label">CPU 使用率</span>
                  <el-progress 
                    type="dashboard" 
                    :percentage="deviceData.cpuUsage" 
                    :color="getHealthColor(deviceData.cpuUsage)"
                  >
                    <template #default="{ percentage }">
                      <span class="percentage-value">{{ percentage }}%</span>
                    </template>
                  </el-progress>
                </div>
                <div class="metric-item">
                  <span class="metric-label">内存使用率</span>
                  <el-progress 
                    type="dashboard" 
                    :percentage="deviceData.memoryUsage" 
                    :color="getHealthColor(deviceData.memoryUsage)"
                  >
                    <template #default="{ percentage }">
                      <span class="percentage-value">{{ percentage }}%</span>
                    </template>
                  </el-progress>
                </div>
                <!-- 服务器显示磁盘使用率 -->
                 <div v-if="!isNetworkDevice" class="metric-item">
                  <span class="metric-label">磁盘使用率</span>
                  <el-progress 
                    type="dashboard" 
                    :percentage="deviceData.diskUsage || 0" 
                    :color="getHealthColor(deviceData.diskUsage || 0)"
                  >
                    <template #default="{ percentage }">
                      <span class="percentage-value">{{ percentage }}%</span>
                    </template>
                  </el-progress>
                </div>
              </div>
              <div class="uptime-info">
                <el-icon><Timer /></el-icon>
                <span>系统运行时间: {{ deviceData.uptime }}</span>
              </div>
            </el-card>
          </div>
        </el-col>

        <!-- 右侧栏：高级监控与管理 -->
        <el-col :span="16">
          <el-card class="tabs-card" shadow="hover">
            <el-tabs v-model="activeTab">
              <!-- Tab 1: 接口面板 (仅网络设备显示) -->
              <el-tab-pane v-if="isNetworkDevice" label="接口面板" name="interfaces">
                <template #label>
                  <span class="custom-tabs-label">
                    <el-icon><Connection /></el-icon>
                    <span>接口面板</span>
                  </span>
                </template>
                <el-table :data="deviceData.interfaces" style="width: 100%" stripe>
                  <el-table-column prop="name" label="接口名称" width="180" />
                  <el-table-column prop="status" label="状态" width="100">
                    <template #default="scope">
                      <el-tag :type="scope.row.status === 'Up' ? 'success' : 'danger'" size="small">
                        {{ scope.row.status }}
                      </el-tag>
                    </template>
                  </el-table-column>
                  <el-table-column prop="ip" label="IP 地址" width="150" />
                  <el-table-column prop="inTraffic" label="入站流量" />
                  <el-table-column prop="outTraffic" label="出站流量" />
                </el-table>
              </el-tab-pane>

              <!-- Tab 1: 进程列表 (仅服务器显示) -->
               <el-tab-pane v-if="!isNetworkDevice" label="进程列表" name="processes">
                <template #label>
                  <span class="custom-tabs-label">
                    <el-icon><Memo /></el-icon>
                    <span>进程列表</span>
                  </span>
                </template>
                <el-empty description="暂无进程数据（需安装 Agent）" />
              </el-tab-pane>

              <!-- Tab 2: 告警日志 -->
              <el-tab-pane label="告警日志" name="alerts">
                 <template #label>
                  <span class="custom-tabs-label">
                    <el-icon><Bell /></el-icon>
                    <span>告警日志</span>
                  </span>
                </template>
                <el-timeline>
                  <el-timeline-item
                    v-for="(activity, index) in deviceData.alerts"
                    :key="index"
                    :icon="activity.icon"
                    :type="activity.type"
                    :color="activity.color"
                    :size="activity.size"
                    :timestamp="activity.timestamp"
                  >
                    {{ activity.content }}
                  </el-timeline-item>
                </el-timeline>
              </el-tab-pane>

              <!-- Tab 3: 配置详情 -->
              <el-tab-pane label="配置详情" name="config">
                 <template #label>
                  <span class="custom-tabs-label">
                    <el-icon><Setting /></el-icon>
                    <span>配置详情</span>
                  </span>
                </template>
                <el-descriptions title="SSH 配置信息" :column="2" border>
                  <el-descriptions-item label="SSH 端口">{{ deviceData.sshPort }}</el-descriptions-item>
                  <el-descriptions-item label="用户名">{{ deviceData.sshUser }}</el-descriptions-item>
                  <el-descriptions-item label="认证方式">密码认证</el-descriptions-item>
                  <el-descriptions-item label="超时时间">300s</el-descriptions-item>
                  <el-descriptions-item label="最后连接时间">{{ deviceData.lastConnect }}</el-descriptions-item>
                  <el-descriptions-item label="备注">
                    <el-tag size="small">自动管理</el-tag>
                  </el-descriptions-item>
                </el-descriptions>
                <div class="config-actions">
                    <el-alert title="敏感信息已脱敏显示，如需查看完整密码请联系管理员。" type="warning" show-icon :closable="false" />
                </div>
              </el-tab-pane>
            </el-tabs>
          </el-card>
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { 
  ArrowLeft, 
  Monitor, 
  Refresh, 
  SwitchButton, 
  InfoFilled, 
  Odometer, 
  Timer, 
  Connection, 
  Bell, 
  Setting,
  Memo 
} from '@element-plus/icons-vue'
import Cookies from 'js-cookie'
import axios from '@/axios/axios'
import { dveiceDateStore } from './Date/index' // 引入 Store
import { homeDataStore } from '@/components/home/home/data'

const route = useRoute()
const router = useRouter()
const store = dveiceDateStore() // 使用 Store
const authStore = homeDataStore()
const deviceId = route.params.id
const loading = ref(false)
const activeTab = ref('interfaces') // 默认值，后续会根据设备类型调整
const timer = ref(null)
const canSsh = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:ssh:connect')))

// 设备数据模型
const deviceData = reactive({
  id: '',
  name: '',
  ip: '',
  status: '',
  type: '', // 设备类型
  vendor: '',
  model: '',
  serialNumber: '',
  location: '',
  snmpVersion: '',
  osVersion: '',
  cpuUsage: 0,
  memoryUsage: 0,
  diskUsage: 0, // 新增磁盘使用率
  uptime: '',
  sshPort: 22,
  sshUser: '',
  lastConnect: '',
  interfaces: [],
  alerts: []
})

// 计算属性：是否为网络设备
const isNetworkDevice = computed(() => {
    const type = deviceData.type ? deviceData.type.toLowerCase() : '';
    return ['router', 'switch', 'firewall', '路由器', '交换机', '防火墙', 'huawei'].includes(type);
});

// 监听设备类型变化，自动切换 Tab
// ...

// 返回列表页
const goBack = () => {
  router.push('/user/device')
}

// 跳转到 SSH 页面
const handleWebSSH = () => {
  if (deviceData.ip) {
    const routeUrl = router.resolve({
        name: 'ssh-connection',
        params: { ip: deviceData.ip }
    });
    window.open(routeUrl.href, '_blank');
  } else {
    ElMessage.warning('设备 IP 不存在')
  }
}

// 重启设备
const handleRestart = () => {
  ElMessageBox.confirm(
    '确定要重启该设备吗？重启过程中将无法采集监控数据。',
    '重启确认',
    {
      confirmButtonText: '确定重启',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(() => {
      ElMessage({
        type: 'success',
        message: '重启指令已下发',
      })
    })
    .catch(() => {
      // 取消操作
    })
}

// 获取健康度颜色
const getHealthColor = (percentage) => {
  if (percentage < 60) return '#67C23A'
  if (percentage < 80) return '#E6A23C'
  return '#F56C6C'
}

// 模拟获取数据
const applyListItemToModel = (item) => {
  if (!item) return
  deviceData.id = item.id
  deviceData.name = item.device_name || ''
  deviceData.ip = item.ipv4 || ''
  deviceData.status = item.status || ''
  deviceData.type = item.type || ''
  deviceData.location = item.location || ''
  deviceData.sshPort = item.ssh_port || 22
  deviceData.cpuUsage = parseFloat(item.cpu_usage || 0)
  deviceData.memoryUsage = parseFloat(item.memory_usage || 0)
  deviceData.diskUsage = parseFloat(item.disk_usage || 0)
}

const fetchDeviceData = async (isSilent = false) => {
  if (!isSilent) {
    loading.value = true
  }
  try {
    const local = (store.data || []).find(d => d.id == deviceId)
    if (local) {
      applyListItemToModel(local)
    } else {
      const response = await axios.get('/api/v1/user/device/get', { params: { type: 0 } })
      const list = Array.isArray(response.data) ? response.data : []
      const remote = list.find(d => d.id == deviceId)
      if (!remote) throw new Error('未找到该设备')
      applyListItemToModel(remote)
    }

    if (!deviceData.type) {
      activeTab.value = 'interfaces'
    } else {
      const newIsNetwork = ['router', 'switch', 'firewall', '路由器', '交换机', '防火墙', 'huawei'].includes(String(deviceData.type).toLowerCase())
      activeTab.value = newIsNetwork ? 'interfaces' : 'processes'
    }

    if (!isSilent) ElMessage.success('数据刷新成功')
  } catch (error) {
    console.error('获取设备详情失败:', error)
    if (!isSilent) {
        ElMessage.error(error.response?.data?.message || '获取设备详情失败')
    }
  } finally {
    if (!isSilent) {
        loading.value = false
    }
  }
}

// WebSocket 实例
const ws = ref(null)
// 标记是否使用全局 WebSocket
const usingGlobalWS = ref(false)

const initWebSocket = () => {
    // 1. 尝试从 Store 中获取数据 (如果列表页的 WebSocket 已经开启)
    
    // 检查 Store 中是否有该设备的数据
    // 注意：store.data 是一个 ref，需要通过 .value 访问，但在组件中直接使用 store.data (如果不解构) 可能需要注意访问方式
    // 检查 index.js 定义： const data = ref([])
    // 在 store 中导出时 return { data, ... }
    // 在组件中使用 const store = dveiceDateStore()
    // 此时 store.data 应该是自动解包的数组，或者需要通过 store.getData() 获取
    
    const deviceList = store.data || [] // 容错处理
    const cachedDevice = deviceList.find(d => d.id == deviceId)
    
    if (cachedDevice) {
      console.log('Using Store data for realtime updates')
      usingGlobalWS.value = true
      
      // 立即同步一次
      syncFromStore(cachedDevice)
      
      // 监听 Store 变化
      // 注意：store.data 是一个数组，我们需要监听其中特定元素的变化
      // 或者更简单：监听整个 data 数组，当 id 匹配时更新
      // 由于 vue 的响应式系统，如果 store.data 中的对象属性发生变化，watch 应该能捕获到
      // 但最好是 watchEffect 或者 watch(() => store.data)
  } else {
      console.log('Store data not found, falling back to dedicated WebSocket')
      usingGlobalWS.value = false
      // ... 原有的 WebSocket 连接逻辑
      connectDedicatedWebSocket()
  }
}

const syncFromStore = (data) => {
    if (!data) return
    deviceData.status = data.status
    // Store 中的数据可能是字符串 "35%"，需要转换
    deviceData.cpuUsage = parseFloat(data.cpu_usage || 0)
    deviceData.memoryUsage = parseFloat(data.memory_usage || 0)
    deviceData.diskUsage = parseFloat(data.disk_usage || 0)
    // deviceData.uptime = data.uptime // Store 中目前没有 uptime
}

// 独立的 WebSocket 连接逻辑 (原 initWebSocket)
const connectDedicatedWebSocket = () => {
  // 确保先关闭旧连接
  if (ws.value) {
    ws.value.close()
  }

  // 构建 WebSocket URL
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const wsBase = `${wsProtocol}//${window.location.host}`
  
  // 从 Cookie 获取 Token 用于鉴权
  const token = Cookies.get('token')
  
  if (!token) {
    console.error('WebSocket init failed: No token found')
    return
  }

  const wsUrl = `${wsBase}/api/v1/user/device/ws/detail/${deviceId}?token=${encodeURIComponent(token)}`
  
  console.log('Connecting to Detail WebSocket:', wsUrl)

  try {
      ws.value = new WebSocket(wsUrl)

      ws.value.onopen = () => {
        console.log('WebSocket connected')
      }

      ws.value.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          // 更新实时数据
          if (data) {
             deviceData.status = data.status
             deviceData.cpuUsage = data.cpuUsage
             deviceData.memoryUsage = data.memoryUsage
             deviceData.diskUsage = data.diskUsage
             deviceData.uptime = data.uptime
             // 更新最后连接时间
             if (data.lastConnect) {
                deviceData.lastConnect = data.lastConnect
             }
             // 更新版本信息（如果有变化）
             if (data.osVersion && data.osVersion !== 'Unknown') {
                deviceData.osVersion = data.osVersion
             }
          }
        } catch (e) {
          console.error('WebSocket message parse error:', e)
        }
      }

      ws.value.onerror = (error) => {
        console.error('WebSocket error:', error)
        // 可以在这里添加重连逻辑
      }

      ws.value.onclose = (e) => {
        console.log('WebSocket closed', e.code, e.reason)
        if (e.code === 4001) {
            ElMessage.error('实时连接认证失败: ' + (e.reason || '请重新登录'))
        }
      }
  } catch (e) {
      console.error('WebSocket creation failed:', e)
  }
}

// 监听 Store 变化 (仅当使用全局 WS 时)
watch(() => store.data, (newData) => {
    if (usingGlobalWS.value) {
        const item = newData.find(d => d.id == deviceId)
        if (item) {
            syncFromStore(item)
        }
    }
}, { deep: true })

onMounted(() => {
  authStore.syncAuthFromToken()
  authStore.fetchPermissions()
  fetchDeviceData()
  // 初始化 WebSocket 连接
  initWebSocket()
})

onUnmounted(() => {
  if (ws.value) {
    ws.value.close()
    ws.value = null
  }
})
</script>

<style scoped>
.device-detail-container {
  padding: 20px;
  background-color: #f5f7fa;
  min-height: calc(100vh - 84px); /* 减去顶部导航的高度 */
}

.page-header-card {
  margin-bottom: 20px;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 15px;
}

.device-title {
  display: flex;
  align-items: center;
  gap: 10px;
}

.device-name {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.device-ip {
  font-family: monospace;
}

.main-content {
  /* 布局调整 */
}

.left-column {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.info-card, .health-card, .tabs-card {
  height: 100%;
}

.card-header {
  display: flex;
  align-items: center;
  font-weight: bold;
}

.card-header .el-icon {
  margin-right: 5px;
  vertical-align: middle;
}

.health-metrics {
  display: flex;
  justify-content: space-around;
  margin-bottom: 20px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.metric-label {
  margin-bottom: 10px;
  font-size: 14px;
  color: #606266;
}

.percentage-value {
  font-size: 20px;
  font-weight: bold;
  color: #303133;
}

.uptime-info {
  text-align: center;
  color: #909399;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border-top: 1px solid #ebeef5;
  padding-top: 15px;
}

.custom-tabs-label .el-icon {
  vertical-align: middle;
  margin-right: 5px;
}

.config-actions {
  margin-top: 20px;
}
</style>
