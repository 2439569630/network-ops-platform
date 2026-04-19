<template>
  <div class="dashboard-container" :class="{ 'is-mobile': isMobile }" v-loading="loading">
    <!-- 1. Statistics Cards -->
    <el-row :gutter="isMobile ? 12 : 20">
      <el-col :span="6" :xs="12" v-for="(stat, index) in statsCards" :key="index" class="stat-col">
        <el-card shadow="hover" class="stat-card" @click="handleCardClick(stat.link)">
          <div class="stat-content">
             <div class="stat-icon" :style="{ background: stat.bgColor }">
                 <el-icon :size="isMobile ? 20 : 24" color="#fff"><component :is="stat.icon" /></el-icon>
             </div>
             <div class="stat-info">
                 <div class="stat-label">{{ stat.label }}</div>
                 <div class="stat-num" :style="{ color: stat.color }">{{ stat.value }}</div>
                 <div class="stat-trend" v-if="!isMobile && typeof stat.trend === 'number'">
                     <span :class="stat.trend >= 0 ? 'up' : 'down'">
                         <el-icon><component :is="stat.trend >= 0 ? 'CaretTop' : 'CaretBottom'" /></el-icon>
                         {{ Math.abs(stat.trend) }}%
                     </span>
                     <span class="trend-text">较昨日</span>
                 </div>
             </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 2. Charts Row -->
    <el-row :gutter="isMobile ? 12 : 20" :class="isMobile ? 'mt-12' : 'mt-20'">
        <!-- Device Status Pie -->
        <el-col :span="12" :xs="24" class="chart-col">
            <el-card shadow="hover" class="chart-card">
                <template #header>
                    <div class="card-header">
                        <span>设备状态分布</span>
                       
                    </div>
                </template>
                <div class="chart-container">
                    <v-chart class="chart" :option="statusChartOption" autoresize />
                </div>
            </el-card>
        </el-col>
        <!-- Alert Distribution Bar -->
        <el-col :span="12" :xs="24" class="chart-col">
             <el-card shadow="hover" class="chart-card">
                <template #header>
                    <div class="card-header">
                        <span>告警级别分布</span>
                        <el-dropdown trigger="click">
                            <span class="el-dropdown-link">{{ alertPeriodLabel }}<el-icon class="el-icon--right"><arrow-down /></el-icon></span>
                            <template #dropdown>
                                <el-dropdown-menu>
                                    <el-dropdown-item @click="setAlertPeriod('today')">今天</el-dropdown-item>
                                    <el-dropdown-item @click="setAlertPeriod('week')">本周</el-dropdown-item>
                                    <el-dropdown-item @click="setAlertPeriod('month')">本月</el-dropdown-item>
                                </el-dropdown-menu>
                            </template>
                        </el-dropdown>
                    </div>
                </template>
                <div class="chart-container">
                    <v-chart class="chart" :option="alertChartOption" autoresize />
                </div>
            </el-card>
        </el-col>
    </el-row>

    <!-- 3. Alert List & Top Resources -->
    <el-row :gutter="isMobile ? 12 : 20" :class="isMobile ? 'mt-12' : 'mt-20'">
      <el-col :span="14" :xs="24" class="list-col">
        <el-card class="box-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <div class="header-left">
                  <span>实时告警列表</span>
                  <span class="alert-window-text">近 1 小时事件</span>
              </div>
              <div class="header-right">
                   <el-radio-group v-model="alertFilter" size="small">
                      <el-radio-button label="all">全部</el-radio-button>
                      <el-radio-button label="critical">严重</el-radio-button>
                      <el-radio-button label="warning">警告</el-radio-button>
                   </el-radio-group>
              </div>
            </div>
          </template>
          <el-table :data="filteredAlerts" style="width: 100%" height="350" :row-class-name="tableRowClassName" :size="isMobile ? 'small' : 'default'">
            <el-table-column prop="level" label="级别" width="80">
                <template #default="{ row }">
                    <el-tag :type="getAlertTagType(row.level)" size="small" effect="dark">{{ row.level }}</el-tag>
                </template>
            </el-table-column>
            <el-table-column prop="device_name" label="设备" width="120" show-overflow-tooltip />
            <el-table-column prop="message" label="内容" show-overflow-tooltip />
            <el-table-column prop="time" label="时间" width="300" v-if="!isMobile" />
          </el-table>
        </el-card>
      </el-col>
      
      <el-col :span="10" :xs="24" class="list-col">
        <el-card class="box-card" shadow="hover">
          <template #header>
            <div class="card-header">
              <span>资源使用 Top 10</span>
              <el-tooltip content="按CPU使用率排序" placement="top">
                  <el-icon><InfoFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>
           <el-table :data="topUsageDevices" style="width: 100%" height="350" :size="isMobile ? 'small' : 'default'">
            <el-table-column prop="device_name" label="设备" width="100" show-overflow-tooltip />
            <el-table-column label="CPU / 内存">
                <template #default="scope">
                    <div class="resource-bar">
                        <span class="label">CPU</span>
                        <el-progress
                          :percentage="getUsagePercentage(scope.row.cpu_usage)"
                          :format="() => formatUsageLabel(scope.row.cpu_usage)"
                          :color="getProgressColor"
                          :stroke-width="6"
                        />
                    </div>
                    <div class="resource-bar mt-5">
                        <span class="label">MEM</span>
                        <el-progress
                          :percentage="getUsagePercentage(scope.row.memory_usage)"
                          :format="() => formatUsageLabel(scope.row.memory_usage)"
                          :color="getProgressColor"
                          :stroke-width="6"
                        />
                    </div>
                </template>
            </el-table-column>
            <el-table-column width="50" fixed="right">
                 <template #default="scope">
                     <el-button :icon="ArrowRight" circle size="small" @click="goToDevice(scope.row)" />
                 </template>
            </el-table-column>
          </el-table>
        </el-card>
      </el-col>
    </el-row>
    
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, reactive, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElNotification } from 'element-plus'
import { 
    Monitor, CircleCheckFilled, CircleCloseFilled, WarningFilled,
    CaretTop, CaretBottom, ArrowRight, InfoFilled, ArrowDown,
    Aim, Document, List, Setting
} from '@element-plus/icons-vue'
import axios from '@/axios/axios'

// ECharts
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'

use([CanvasRenderer, PieChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const router = useRouter()

const isMobile = ref(window.innerWidth < 768)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }

// State
const loading = ref(false)
const refreshTimer = ref(null)
const alertClockTimer = ref(null)
const alertFilter = ref('all')
const alertPeriod = ref('week')
const alertNowTs = ref(Date.now())
const ALERT_WINDOW_MS = 60 * 60 * 1000
const alertPeriodLabel = computed(() => {
    const map = { today: '今天', week: '本周', month: '本月' }
    return map[alertPeriod.value] || '本周'
})

const overviewData = ref(null)
const monitorHealth = ref(null)
const alerts = ref([])
const alertStatsData = reactive({ xAxis: [], series: [] })

let ws = null
let manualClose = false
let reconnectAttempts = 0
let reconnectTimer = null

const normalizeHostname = (hostname) => {
    const h = String(hostname || '').trim()
    if (!h || h === '0.0.0.0') return '127.0.0.1'
    return h
}

const normalizeAlertLevel = (value) => {
    const raw = String(value || '').trim()
    const low = raw.toLowerCase()
    if (raw === '严重' || low === 'critical' || low === 'error' || low === 'fatal') return '严重'
    if (raw === '警告' || low === 'warning' || low === 'warn') return '警告'
    if (raw === '提醒' || low === 'info' || low === 'notice') return '提醒'
    return raw || '提醒'
}

const mapAlertRow = (payload) => {
    const level = normalizeAlertLevel(payload?.level)
    const deviceName = String(payload?.device_name || payload?.deviceName || payload?.device || '')
    const desc = String(payload?.description || payload?.message || '')
    const time = String(payload?.time || '')
    return {
        level,
        device_name: deviceName || '-',
        message: desc || '-',
        time: time || '-',
        raw: payload || null,
    }
}

const parseAlertTime = (value) => {
    const raw = String(value || '').trim()
    if (!raw || raw === '-') return null
    const ts = Date.parse(raw)
    return Number.isFinite(ts) ? ts : null
}

const formatAlertTime = (value) => {
    const ts = parseAlertTime(value)
    if (ts === null) return String(value || '-')
    return new Date(ts).toLocaleString('zh-CN', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false,
    })
}

const isOfflineAlert = (row) => String(row?.message || '').startsWith('设备离线')
const isRecoveredAlert = (row) => {
    const msg = String(row?.message || '')
    return msg.startsWith('设备已恢复在线') || msg.startsWith('设备已在线超过')
}

const closeWs = () => {
    manualClose = true
    if (reconnectTimer) {
        clearTimeout(reconnectTimer)
        reconnectTimer = null
    }
    if (ws) {
        try {
            ws.close()
        } catch {}
        ws = null
    }
}

const openWs = () => {
    try {
        if (!sessionStorage.getItem('auth:session_cache:v1')) return
    } catch {}

    closeWs()
    manualClose = false

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsHost = normalizeHostname(window.location.hostname)
    const wsPort = window.location.port ? `:${window.location.port}` : ''
    const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/dashboard/ws/overview`

    try {
        ws = new WebSocket(wsUrl)
    } catch {
        ws = null
        return
    }

    ws.onopen = () => {
        reconnectAttempts = 0
    }

    ws.onmessage = (event) => {
        let msg = null
        try {
            msg = JSON.parse(event.data)
        } catch {
            msg = null
        }
        if (!msg || typeof msg !== 'object') return

        const type = String(msg.type || '').trim()
        const data = msg.data

        if (type === 'init') {
            overviewData.value = data?.overview || null
            monitorHealth.value = data?.monitor_health || null
            if (data?.alert_level_dist) {
                alertStatsData.xAxis = data.alert_level_dist.xAxis || []
                alertStatsData.series = data.alert_level_dist.series || []
            }
            const initAlerts = Array.isArray(data?.alerts_recent) ? data.alerts_recent : []
            alerts.value = initAlerts.map(mapAlertRow)
            loading.value = false
            return
        }

        if (type === 'overview') {
            overviewData.value = data || null
            return
        }

        if (type === 'monitor_health') {
            monitorHealth.value = data || null
            return
        }

        if (type === 'alert_level_dist') {
            alertStatsData.xAxis = data?.xAxis || []
            alertStatsData.series = data?.series || []
            return
        }

        if (type === 'alert') {
            const row = mapAlertRow(data)
            alerts.value.unshift(row)
            if (alerts.value.length > 50) alerts.value.length = 50
        }
    }

    ws.onclose = async (e) => {
        ws = null
        if (manualClose) return

        const code = Number(e?.code || 0)
        if (code === 4003) {
            ElMessage.warning('无权限查看系统总览')
            return
        }

        if (code === 4001) {
            try {
                await axios.post('/api/v1/auth/refresh')
                reconnectAttempts = 0
                openWs()
            } catch {
                return
            }
            return
        }

        const delay = Math.min(30000, 1000 * Math.pow(2, reconnectAttempts))
        reconnectAttempts++
        reconnectTimer = setTimeout(() => {
            openWs()
        }, delay)
    }
}

const sendRefresh = () => {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        openWs()
        return
    }
    try {
        ws.send(JSON.stringify({ type: 'refresh' }))
    } catch {}
}

const setAlertPeriod = (period) => {
    const p = String(period || '').trim()
    if (!p) return
    alertPeriod.value = p
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        openWs()
        return
    }
    try {
        ws.send(JSON.stringify({ type: 'set_alert_period', period: p }))
    } catch {}
}

// Initial Data Load
onMounted(async () => {
    window.addEventListener('resize', checkMobile)
    loading.value = true
    openWs()
    startAutoRefresh()
    startAlertClock()
})

onUnmounted(() => {
    stopAutoRefresh()
    closeWs()
})

onBeforeUnmount(() => {
    window.removeEventListener('resize', checkMobile)
})

const startAutoRefresh = () => {
    stopAutoRefresh()
    refreshTimer.value = setInterval(() => {
        sendRefresh()
    }, 15000)
}

const stopAutoRefresh = () => {
    if (refreshTimer.value) {
        clearInterval(refreshTimer.value)
        refreshTimer.value = null
    }
    if (alertClockTimer.value) {
        clearInterval(alertClockTimer.value)
        alertClockTimer.value = null
    }
}

const startAlertClock = () => {
    alertNowTs.value = Date.now()
    if (alertClockTimer.value) {
        clearInterval(alertClockTimer.value)
    }
    alertClockTimer.value = setInterval(() => {
        alertNowTs.value = Date.now()
    }, 30000)
}

// Computed Stats
const devicesData = computed(() => overviewData.value?.devices || null)
const totalCount = computed(() => Number(devicesData.value?.total || 0))
const onlineCount = computed(() => Number(devicesData.value?.online || 0))
const offlineCount = computed(() => Number(devicesData.value?.offline || 0))

const visibleAlerts = computed(() => {
    const rows = [...alerts.value]
        .map((row) => ({
            ...row,
            timestamp: parseAlertTime(row.time),
            time: formatAlertTime(row.time),
        }))
        .filter((row) => row.timestamp === null || alertNowTs.value - row.timestamp <= ALERT_WINDOW_MS)
        .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))

    const recoveredDevices = new Set()
    const result = []

    for (const row of rows) {
        const deviceKey = String(row.device_name || '').trim()
        if (isRecoveredAlert(row)) {
            if (deviceKey) recoveredDevices.add(deviceKey)
            result.push(row)
            continue
        }
        if (isOfflineAlert(row) && deviceKey && recoveredDevices.has(deviceKey)) {
            continue
        }
        result.push(row)
    }

    return result.slice(0, 50)
})

const filteredAlerts = computed(() => {
    if (alertFilter.value === 'all') return visibleAlerts.value
    const levelMap = { critical: '严重', warning: '警告' }
    return visibleAlerts.value.filter(a => a.level === levelMap[alertFilter.value])
})

const statsCards = computed(() => [
    { label: '总设备数', value: totalCount.value, icon: Monitor, color: '#409EFF', bgColor: '#409EFF', link: '/user/device' },
    { label: '在线设备', value: onlineCount.value, icon: CircleCheckFilled, color: '#67C23A', bgColor: '#67C23A', link: '/user/device' },
    { label: '离线设备', value: offlineCount.value, icon: CircleCloseFilled, color: '#F56C6C', bgColor: '#F56C6C', link: '/user/device' },
    { label: '系统告警', value: visibleAlerts.value.length, icon: WarningFilled, color: '#E6A23C', bgColor: '#E6A23C', link: '/user/message' }
])

// Charts Options
const statusChartOption = computed(() => {
    const by = devicesData.value?.by_display_status || {}
    const colorMap = {
        在线: '#67C23A',
        离线: '#F56C6C',
        异常: '#E6A23C',
        采集中: '#409EFF',
        检查中: '#409EFF',
        等待重试: '#909399',
        恢复中: '#E6A23C',
        降级: '#E6A23C',
    }
    const data = Object.keys(by).map((k) => ({
        name: k,
        value: Number(by[k] || 0),
        itemStyle: colorMap[k] ? { color: colorMap[k] } : undefined,
    }))
    const fallback = [
        { value: onlineCount.value, name: '在线', itemStyle: { color: '#67C23A' } },
        { value: offlineCount.value, name: '离线', itemStyle: { color: '#F56C6C' } },
    ]
    return {
        tooltip: { trigger: 'item' },
        legend: { bottom: 4, left: 'center', itemWidth: 10, itemHeight: 10, textStyle: { color: '#606266' } },
        series: [
            {
                name: '设备状态',
                type: 'pie',
                radius: ['38%', '68%'],
                center: ['50%', '46%'],
                avoidLabelOverlap: false,
                itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
                label: { show: false, position: 'center' },
                emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
                labelLine: { show: false },
                data: data.length ? data : fallback,
            },
        ],
    }
})

const alertChartOption = computed(() => {
    const period = String(alertPeriod.value || 'week')
    const xAxisData = alertStatsData.xAxis.length
        ? alertStatsData.xAxis
        : (period === 'today'
            ? ['00:00', '06:00', '12:00', '18:00']
            : ['04-01', '04-02', '04-03', '04-04', '04-05', '04-06', '04-07'])
    const palette = {
        严重: '#F56C6C',
        警告: '#E6A23C',
        提醒: '#409EFF',
    }
    const fallbackSeries = ['严重', '警告', '提醒'].map((name) => ({
        name,
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        showSymbol: xAxisData.length <= 12,
        lineStyle: { width: 3, color: palette[name] },
        itemStyle: { color: palette[name] },
        areaStyle: { opacity: 0.08, color: palette[name] },
        emphasis: { focus: 'series' },
        data: xAxisData.map(() => 0),
    }))
    const series = alertStatsData.series.length
        ? alertStatsData.series.map((item) => {
            const name = String(item?.name || '')
            const color = palette[name] || '#409EFF'
            return {
                name,
                type: 'line',
                smooth: true,
                symbol: 'circle',
                symbolSize: 7,
                showSymbol: xAxisData.length <= 12,
                lineStyle: { width: 3, color },
                itemStyle: { color },
                areaStyle: { opacity: 0.08, color },
                emphasis: { focus: 'series' },
                data: Array.isArray(item?.data) ? item.data : [],
            }
        })
        : fallbackSeries

    return {
        color: Object.values(palette),
        tooltip: { trigger: 'axis', axisPointer: { type: 'line' } },
        legend: { top: 0, right: 0, itemWidth: 10, itemHeight: 10, textStyle: { color: '#606266' } },
        grid: { left: 16, right: 18, top: 36, bottom: 42, containLabel: true },
        xAxis: {
            type: 'category',
            boundaryGap: false,
            data: xAxisData,
            axisLabel: {
                color: '#606266',
                interval: period === 'month' ? 'auto' : 0,
                rotate: period === 'month' ? 45 : 0,
                hideOverlap: true,
                formatter: (value) => {
                    const text = String(value || '')
                    return text.length > 8 ? `${text.slice(0, 8)}...` : text
                },
            },
        },
        yAxis: {
            type: 'value',
            minInterval: 1,
            splitLine: { lineStyle: { color: '#ebeef5' } },
            axisLabel: { color: '#606266' },
        },
        series,
    }
})

const topUsageDevices = computed(() => {
    const list = Array.isArray(overviewData.value?.top_usage) ? overviewData.value.top_usage : []
    return list
})

// Helpers
const getUsagePercentage = (value) => {
    const raw = String(value ?? '').trim()
    if (!raw || raw === '--') return 0
    const numeric = Number.parseFloat(raw.replace(/%$/, ''))
    if (!Number.isFinite(numeric)) return 0
    return Math.max(0, Math.min(100, numeric))
}

const formatUsageLabel = (value) => {
    const raw = String(value ?? '').trim()
    if (!raw || raw === '--') return '--'
    const numeric = Number.parseFloat(raw.replace(/%$/, ''))
    if (!Number.isFinite(numeric)) return '--'
    return `${numeric}%`
}

const getProgressColor = (percentage) => {
    if (percentage < 60) return '#67c23a';
    if (percentage < 85) return '#e6a23c';
    return '#f56c6c';
};

const getAlertTagType = (level) => {
    const map = { '严重': 'danger', '警告': 'warning', '提醒': 'info' }
    return map[level] || 'info'
}

const tableRowClassName = ({ row }) => {
    if (row.level === '严重') return 'warning-row'
    return ''
}

// Actions
const handleCardClick = (link) => {
    if(link) router.push(link)
}

const goToDevice = (row) => {
    router.push({ name: 'device', query: { search: row.device_name } }) // Assuming device list supports query
}

const handleAlertAction = (row, type) => {
    if (type === 'check') {
        ElNotification({ title: '告警详情', message: `设备: ${row.device_name}\n信息: ${row.message}`, type: 'info' })
    } else {
        ElMessage.success('告警已标记为处理中')
    }
}

</script>

<style scoped>
.dashboard-container {
    padding: 20px;
    background-color: #f3f6fb;
    min-height: 100vh;
}

.dashboard-container.is-mobile {
    padding: 12px;
}

.dashboard-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 20px;
}

.is-mobile .dashboard-header {
    margin-bottom: 12px;
}

.left-title h2 { margin: 0; display: inline-block; margin-right: 15px; }

/* Stat Cards */
.stat-card {
    cursor: pointer;
    transition: all 0.3s;
    border: none;
}
.stat-card:hover {
    transform: translateY(-5px);
    box-shadow: 0 10px 20px rgba(0,0,0,0.1);
}

.is-mobile .stat-card:hover {
    transform: none;
    box-shadow: none;
}

.stat-content {
    display: flex;
    align-items: center;
}

.is-mobile .stat-content {
    flex-direction: column;
    align-items: flex-start;
}

.stat-icon {
    width: 50px;
    height: 50px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    margin-right: 15px;
}

.is-mobile .stat-icon {
    width: 36px;
    height: 36px;
    margin-bottom: 8px;
    margin-right: 0;
}

.stat-label { font-size: 14px; color: #909399; }
.is-mobile .stat-label { font-size: 12px; }

.stat-num { font-size: 24px; font-weight: bold; margin: 5px 0; }
.is-mobile .stat-num { font-size: 18px; margin: 4px 0; }

.stat-trend { font-size: 12px; display: flex; gap: 5px; }
.up { color: #F56C6C; display: flex; align-items: center; }
.down { color: #67C23A; display: flex; align-items: center; }
.trend-text { color: #C0C4CC; }

/* Mobile Grid Adjustments */
.stat-col {
    margin-bottom: 12px;
}
.chart-col {
    margin-bottom: 12px;
}
.list-col {
    margin-bottom: 12px;
}

/* Charts */
.chart-card {
    height: 380px;
    display: flex;
    flex-direction: column;
}

.is-mobile .chart-card {
    height: 320px;
}

.chart-container {
    width: 100%;
    flex: 1;
    min-height: 260px;
}

.is-mobile .chart-container {
    min-height: 220px;
}

.chart {
    height: 100%;
    width: 100%;
}
.card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

/* Alert List & Resources */
.header-left { display: flex; align-items: center; }
.alert-window-text {
    margin-left: 10px;
    font-size: 12px;
    color: #909399;
}
.ml-10 { margin-left: 10px; }
.mt-5 { margin-top: 5px; }
.mt-12 { margin-top: 12px; }
.mt-20 { margin-top: 20px; }
.resource-bar {
    display: flex;
    align-items: center;
}
.resource-bar .label {
    width: 35px;
    font-size: 12px;
    color: #606266;
    font-weight: 500;
}
.resource-bar .el-progress {
    flex: 1;
}

:deep(.chart-card .el-card__body) {
    flex: 1;
    display: flex;
    flex-direction: column;
    padding: 12px 14px;
    overflow: visible;
}

:deep(.chart-card .el-card__header) {
    padding: 12px 14px;
}

:deep(.el-progress-bar__outer) {
    border-radius: 999px;
    background-color: #e9eef7;
}

:deep(.el-progress-bar__inner) {
    border-radius: 999px;
}

/* Responsive */
@media (max-width: 768px) {
    .mt-20 { margin-top: 10px; }
}
</style>
