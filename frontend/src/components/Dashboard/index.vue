<template>
  <div class="dashboard-container" :class="{ 'is-mobile': isMobile }" v-loading="loading">
    <!-- Header Controls -->
    <div class="dashboard-header">
         <div class="left-title">
             <h2>系统总览</h2>
             <span class="update-time" v-if="lastUpdateTime && !isMobile">更新于: {{ lastUpdateTime }}</span>
         </div>
         <div class="right-actions">
             <el-switch v-if="!isMobile" v-model="autoRefresh" active-text="自动刷新" inactive-text="暂停" @change="handleAutoRefreshChange" />
             <el-button :icon="Refresh" circle @click="refreshData" :loading="refreshing" class="ml-10" />
             <el-button v-if="!isMobile" :icon="FullScreen" circle @click="toggleFullScreen" class="ml-10" />
         </div>
    </div>

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
                 <div class="stat-trend" v-if="!isMobile">
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
        <el-col :span="8" :xs="24" class="chart-col">
            <el-card shadow="hover" class="chart-card">
                <template #header>
                    <div class="card-header">
                        <span>设备状态分布</span>
                        <el-tag size="small">实时</el-tag>
                    </div>
                </template>
                <div class="chart-container">
                    <v-chart class="chart" :option="statusChartOption" autoresize />
                </div>
            </el-card>
        </el-col>
        <!-- Alert Distribution Bar -->
        <el-col :span="8" :xs="24" class="chart-col">
             <el-card shadow="hover" class="chart-card">
                <template #header>
                    <div class="card-header">
                        <span>告警级别分布</span>
                        <el-dropdown trigger="click">
                            <span class="el-dropdown-link">本周<el-icon class="el-icon--right"><arrow-down /></el-icon></span>
                            <template #dropdown>
                                <el-dropdown-menu>
                                    <el-dropdown-item>今天</el-dropdown-item>
                                    <el-dropdown-item>本周</el-dropdown-item>
                                    <el-dropdown-item>本月</el-dropdown-item>
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
        <!-- Resource Trend Line -->
        <el-col :span="8" :xs="24" class="chart-col">
             <el-card shadow="hover" class="chart-card">
                <template #header>
                    <div class="card-header">
                        <span>资源使用趋势 (24h)</span>
                    </div>
                </template>
                <div class="chart-container">
                    <v-chart class="chart" :option="resourceTrendOption" autoresize />
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
                  <el-badge :value="alerts.length" class="ml-10" :type="alerts.length > 0 ? 'danger' : 'info'" />
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
            <el-table-column prop="time" label="时间" width="100" v-if="!isMobile" />
            <el-table-column label="操作" width="100" align="center" fixed="right">
                 <template #default="{ row }">
                     <el-button link type="primary" size="small" @click="handleAlertAction(row, 'check')">查看</el-button>
                     <el-button link type="success" size="small" @click="handleAlertAction(row, 'resolve')">处理</el-button>
                 </template>
            </el-table-column>
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
                        <el-progress :percentage="parseFloat(scope.row.cpu_usage || 0)" :color="getProgressColor" :stroke-width="6" />
                    </div>
                    <div class="resource-bar mt-5">
                        <span class="label">MEM</span>
                        <el-progress :percentage="parseFloat(scope.row.memory_usage || 0)" :color="getProgressColor" :stroke-width="6" />
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
import { computed, onMounted, onUnmounted, ref, reactive, watch, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useDeviceStore } from '@/components/DeviceList/store'
import { ElMessage, ElNotification } from 'element-plus'
import { 
    Refresh, FullScreen, Monitor, CircleCheckFilled, CircleCloseFilled, WarningFilled,
    CaretTop, CaretBottom, ArrowRight, InfoFilled, ArrowDown,
    Aim, Document, List, Setting
} from '@element-plus/icons-vue'

// ECharts
import VChart from 'vue-echarts'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { PieChart, BarChart, LineChart } from 'echarts/charts'
import { TitleComponent, TooltipComponent, LegendComponent, GridComponent } from 'echarts/components'

use([CanvasRenderer, PieChart, BarChart, LineChart, TitleComponent, TooltipComponent, LegendComponent, GridComponent])

const router = useRouter()
const store = useDeviceStore()

const isMobile = ref(window.innerWidth < 768)
const checkMobile = () => { isMobile.value = window.innerWidth < 768 }

// State
const loading = ref(false)
const refreshing = ref(false)
const autoRefresh = ref(true)
const refreshTimer = ref(null)
const lastUpdateTime = ref('')
const alertFilter = ref('all')

// Real-time Resource History
const resourceHistory = ref([])
// Alert Statistics
const alertStatsData = reactive({
    xAxis: [],
    series: []
})

// Initial Data Load
onMounted(async () => {
    window.addEventListener('resize', checkMobile)
    loading.value = true
    await refreshData()
    loading.value = false
    
    if (autoRefresh.value) {
        startAutoRefresh()
    }
})

onUnmounted(() => {
    stopAutoRefresh()
    // store.stopPolling() // App.vue manages global connection
})

onBeforeUnmount(() => {
    window.removeEventListener('resize', checkMobile)
})

const startAutoRefresh = () => {
    stopAutoRefresh()
    refreshTimer.value = setInterval(() => {
        refreshData(true) // Silent refresh
    }, 10000) // 10s refresh for dashboard
}

const stopAutoRefresh = () => {
    if (refreshTimer.value) {
        clearInterval(refreshTimer.value)
        refreshTimer.value = null
    }
}

const handleAutoRefreshChange = (val) => {
    if (val) startAutoRefresh()
    else stopAutoRefresh()
}

const refreshData = async (silent = false) => {
    if (!silent) refreshing.value = true
    try {
        store.refreshData()
        fetchAlertStats()
        lastUpdateTime.value = new Date().toLocaleTimeString()
        if (!silent) ElMessage.success('数据已刷新')
    } catch (e) {
        // Error handled in store usually
    } finally {
        if (!silent) refreshing.value = false
    }
}

const fetchAlertStats = async () => {
    try {
        const res = await axios.get('/api/v1/alerts/statistics')
        if (res.data) {
            alertStatsData.xAxis = res.data.xAxis
            alertStatsData.series = res.data.series
        }
    } catch (e) {
        console.error("Failed to fetch alert stats", e)
    }
}

const toggleFullScreen = () => {
    if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen()
    } else {
        if (document.exitFullscreen) {
            document.exitFullscreen()
        }
    }
}

// Computed Stats
const deviceData = computed(() => store.data)
const totalCount = computed(() => deviceData.value.length)
const onlineCount = computed(() => deviceData.value.filter(d => d.status === '在线').length)
const offlineCount = computed(() => deviceData.value.filter(d => d.status !== '在线').length)

// Alerts Logic
const alerts = computed(() => {
    const list = []
    deviceData.value.forEach(d => {
        if (d.status !== '在线') {
            list.push({ level: '严重', device_name: d.device_name, ip: d.ipv4, message: '设备离线', time: '刚刚' })
        }
        if (parseFloat(d.cpu_usage) > 85) {
            list.push({ level: '警告', device_name: d.device_name, ip: d.ipv4, message: `CPU负载高: ${d.cpu_usage}`, time: '刚刚' })
        }
        if (parseFloat(d.memory_usage) > 90) {
            list.push({ level: '警告', device_name: d.device_name, ip: d.ipv4, message: `内存不足: ${d.memory_usage}`, time: '刚刚' })
        }
    })
    return list
})

const filteredAlerts = computed(() => {
    if (alertFilter.value === 'all') return alerts.value
    const levelMap = { critical: '严重', warning: '警告' }
    return alerts.value.filter(a => a.level === levelMap[alertFilter.value])
})

const statsCards = computed(() => [
    { label: '总设备数', value: totalCount.value, icon: 'Monitor', color: '#409EFF', bgColor: '#ecf5ff', trend: 5, link: '/user/device' },
    { label: '在线设备', value: onlineCount.value, icon: 'CircleCheckFilled', color: '#67C23A', bgColor: '#f0f9eb', trend: 2, link: '/user/device' },
    { label: '离线设备', value: offlineCount.value, icon: 'CircleCloseFilled', color: '#F56C6C', bgColor: '#fef0f0', trend: -10, link: '/user/device' }, // Negative trend is good here logically, but showing trend direction
    { label: '系统告警', value: alerts.value.length, icon: 'WarningFilled', color: '#E6A23C', bgColor: '#fdf6ec', trend: 15, link: '/user/message' }
])

// Charts Options
const statusChartOption = computed(() => ({
    tooltip: { trigger: 'item' },
    legend: { bottom: '0%', left: 'center' },
    series: [
        {
            name: '设备状态',
            type: 'pie',
            radius: ['40%', '70%'],
            avoidLabelOverlap: false,
            itemStyle: { borderRadius: 10, borderColor: '#fff', borderWidth: 2 },
            label: { show: false, position: 'center' },
            emphasis: { label: { show: true, fontSize: 20, fontWeight: 'bold' } },
            labelLine: { show: false },
            data: [
                { value: onlineCount.value, name: '在线', itemStyle: { color: '#67C23A' } },
                { value: offlineCount.value, name: '离线', itemStyle: { color: '#F56C6C' } },
                { value: 0, name: '维护中', itemStyle: { color: '#E6A23C' } } // Placeholder
            ]
        }
    ]
}))

const alertChartOption = computed(() => ({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
    xAxis: { type: 'category', data: alertStatsData.xAxis.length ? alertStatsData.xAxis : ['暂无数据'] },
    yAxis: { type: 'value' },
    series: alertStatsData.series.length ? alertStatsData.series : [
        { name: '严重', type: 'bar', stack: 'total', data: [], itemStyle: { color: '#F56C6C' } },
        { name: '警告', type: 'bar', stack: 'total', data: [], itemStyle: { color: '#E6A23C' } },
        { name: '提醒', type: 'bar', stack: 'total', data: [], itemStyle: { color: '#909399' } }
    ]
}))

const resourceTrendOption = computed(() => {
    const times = resourceHistory.value.map(item => item.time)
    const cpuData = resourceHistory.value.map(item => item.cpu)
    const memData = resourceHistory.value.map(item => item.mem)
    
    return {
        tooltip: { trigger: 'axis' },
        legend: { data: ['CPU平均', '内存平均'] },
        grid: { left: '3%', right: '4%', bottom: '3%', containLabel: true },
        xAxis: { type: 'category', boundaryGap: false, data: times },
        yAxis: { type: 'value', max: 100 },
        series: [
            { name: 'CPU平均', type: 'line', smooth: true, data: cpuData, itemStyle: { color: '#409EFF' }, areaStyle: { opacity: 0.1 } },
            { name: '内存平均', type: 'line', smooth: true, data: memData, itemStyle: { color: '#67C23A' }, areaStyle: { opacity: 0.1 } }
        ]
    }
})

// Watch device data for real-time trend
watch(deviceData, (newVal) => {
    if (!newVal) return
    
    const now = new Date().toLocaleTimeString()
    let avgCpu = 0
    let avgMem = 0
    
    const onlineDevs = newVal.filter(d => d.status === '在线')
    if (onlineDevs.length > 0) {
        const totalCpu = onlineDevs.reduce((sum, d) => sum + (parseFloat(d.cpu_usage) || 0), 0)
        const totalMem = onlineDevs.reduce((sum, d) => sum + (parseFloat(d.memory_usage) || 0), 0)
        avgCpu = (totalCpu / onlineDevs.length).toFixed(1)
        avgMem = (totalMem / onlineDevs.length).toFixed(1)
    }
    
    resourceHistory.value.push({ time: now, cpu: avgCpu, mem: avgMem })
    
    if (resourceHistory.value.length > 20) {
        resourceHistory.value.shift()
    }
})

const topUsageDevices = computed(() => {
    return [...deviceData.value].sort((a, b) => {
        return parseFloat(b.cpu_usage || 0) - parseFloat(a.cpu_usage || 0)
    }).slice(0, 10)
})

// Helpers
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
    background-color: #f5f7fa;
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
.update-time { font-size: 12px; color: #909399; }

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
    height: 350px;
    display: flex;
    flex-direction: column;
}

.is-mobile .chart-card {
    height: 300px;
}

.chart-container {
    height: 280px;
    width: 100%;
}

.is-mobile .chart-container {
    height: 230px;
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
    color: #909399;
}
.resource-bar .el-progress {
    flex: 1;
}

/* Responsive */
@media (max-width: 768px) {
    .mt-20 { margin-top: 10px; }
}
</style>