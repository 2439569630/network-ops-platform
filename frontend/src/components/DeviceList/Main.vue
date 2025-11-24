<template>
    <!-- 设备列表主容器 -->
    <div :class="$style.deviceListMain">

        <!-- 头部区域 -->
        <div :class="[$style.headerBody]">
            <!-- 视图切换按钮组 -->
            <el-button-group :class="$style.buttonGroup">
                <!-- 卡片视图按钮 -->
                <el-button type="primary" :class="{
                    [$style.buttonActive]: setCardData,
                    [$style.buttonInactive]: !setCardData
                }" @click="Ddevice_List_date.setdataCardType(0)" :icon="Grid" />
                <!-- 列表视图按钮 -->
                <el-button type="primary" :class="{
                    [$style.buttonActive]: !setCardData,
                    [$style.buttonInactive]: setCardData
                }" @click="Ddevice_List_date.setdataCardType(1)" :icon="List" />
            </el-button-group>
            <!-- 设备类型标签页 -->
            <el-header :class="[$style.headerTop]" v-if="!Ddevice_List_date.getdataCardType()">
                <el-tabs v-model="activeName" :class="[$style.demoTabs, $style.tabsDeviceList]"
                    @tab-click="handleClick">
                    <el-tab-pane label="全部设备" name="0"></el-tab-pane>
                    <el-tab-pane label="路由器" name="1"></el-tab-pane>
                    <el-tab-pane label="交换机" name="2"></el-tab-pane>
                    <el-tab-pane label="防火墙" name="3"></el-tab-pane>
                    <el-tab-pane label="服务器" name="4"></el-tab-pane>
                </el-tabs>
            </el-header>
        </div>
        <!-- 主内容区域 -->
        <el-main :class="{
            [$style.mainDeviceListDefaultCard]: setCardData,
            [$style.mainDeviceListDefaultList]: !setCardData
        }" max-height="40px" :style="{ paddingTop: setCardData ? '30px' : '0px' }">
            <!-- 卡片 -->
            <el-card v-if="setCardData" v-for="(item, index) in Ddevice_List_date.getData()" :key="index"
                :class="{ [$style.cardDeviceList]: setCardData }" shadow="hover">
                <template #header>
                    <div :class="$style.cardHeader">
                        <span>{{ item.device_name }}</span>
                        <el-tag :type="item.status === '在线' ? 'success' : 'danger'" size="small" effect="dark">
                            {{ item.status }}
                        </el-tag>
                    </div>
                </template>
                <div :class="$style.cardContent">
                    <div :class="$style.cardInfo">
                        <div :class="$style.infoItem">
                            <span :class="$style.infoLabel">设备类型</span>
                            <span :class="$style.infoValue">{{ item.type }}</span>
                        </div>
                        <div :class="$style.infoItem">
                            <span :class="$style.infoLabel">位置</span>
                            <span :class="$style.infoValue">{{ item.location }}</span>
                        </div>
                        <div :class="$style.infoItem">
                            <span :class="$style.infoLabel">IPv4</span>
                            <span :class="$style.infoValue">{{ item.ipv4 }}</span>
                        </div>
                        <div :class="$style.infoItem">
                            <span :class="$style.infoLabel">MAC</span>
                            <span :class="$style.infoValue" :title="item.mac">{{ formatMac(item.mac) }}</span>
                        </div>
                    </div>
                    <div :class="$style.cardStats">
                        <div :class="$style.statItem">
                            <div :class="$style.statLabel">
                                <span>CPU使用率</span>
                                <span :class="$style.statValue">{{ item.cpu_usage || '0' }}%</span>
                            </div>
                            <el-progress :percentage="parseFloat(item.cpu_usage || 0)" :color="getProgressColor(parseFloat(item.cpu_usage || 0))" :show-text="false" :stroke-width="8" />
                        </div>
                        <div :class="$style.statItem">
                            <div :class="$style.statLabel">
                                <span>内存使用率</span>
                                <span :class="$style.statValue">{{ item.memory_usage || '0' }}%</span>
                            </div>
                            <el-progress :percentage="parseFloat(item.memory_usage || 0)" :color="getProgressColor(parseFloat(item.memory_usage || 0))" :show-text="false" :stroke-width="8" />
                        </div>
                        <div :class="$style.statItem">
                            <div :class="$style.statLabel">
                                <span>磁盘使用率</span>
                                <span :class="$style.statValue">{{ item.disk_usage || '0' }}%</span>
                            </div>
                            <el-progress :percentage="parseFloat(item.disk_usage || 0)" :color="getProgressColor(parseFloat(item.disk_usage || 0))" :show-text="false" :stroke-width="8" />
                        </div>
                    </div>
                    <div :class="$style.cardActions">
                        <el-button type="primary" size="small" :icon="View" @click="showDeviceDetail(item)">
                            详情
                        </el-button>
                        <el-button type="success" size="small" :icon="Connection" @click="connectSSH(item)" :disabled="item.status !== '在线'">
                            SSH连接
                        </el-button>
                    </div>
                </div>
            </el-card>

            <!-- 列表 -->
            <el-table v-if="!setCardData" :data="Ddevice_List_date.getData()" :style="[$style.tableDeviceList]" :row-class-name="tableRowClassName" height="100%" :header-cell-style="{backgroundColor: 'rgba(255, 255, 255, 0.2)'}" :default-sort="{ prop: 'device_name', order: 'ascending' }">
                <el-table-column prop="device_name" label="设备名称" width="180" sortable />
                <el-table-column prop="ipv4" label="IPv4地址" width="180" sortable />
                <el-table-column prop="ipv6" label="IPv6地址" width="240" sortable />
                <el-table-column prop="mac" label="MAC地址" width="180" sortable />
                <el-table-column prop="status" label="状态" width="120" sortable :sort-method="sortStatus">
                    <template #default="scope">
                        <el-tag :type="scope.row.status === '在线' ? 'success' : 'danger'">
                            {{ scope.row.status }}
                        </el-tag>
                    </template>
                </el-table-column>
                <el-table-column prop="type" label="设备类型" width="120" sortable />
                <el-table-column prop="location" label="位置" width="120" sortable />
                <el-table-column prop="cpu_usage" label="CPU使用率" width="120" sortable :sort-method="sortByPercentage" />
                <el-table-column prop="memory_usage" label="内存使用率" width="120" sortable :sort-method="sortByPercentage" />
                <el-table-column prop="disk_usage" label="磁盘使用率" width="120" sortable :sort-method="sortByPercentage" />
                <el-table-column prop="network_traffic" label="网络流量" width="120" sortable :sort-method="sortByNetworkTraffic" />
                <el-table-column prop="network_connections" label="网络连接数" width="120" sortable :sort-method="sortByNumber" />
            </el-table>
        </el-main>
    </div>
</template>

<script setup>
import { ref, computed } from 'vue';
import { Grid, List, View, Connection  } from '@element-plus/icons-vue'
import { dveiceDateStore } from './Date/index'

const Ddevice_List_date = dveiceDateStore()
const activeName = ref('0')

// 移除tableData，直接使用store中的数据
// 计算卡片的切换
const setCardData = computed(() => {
    return Ddevice_List_date.getdataCardType() === 0
})

const handleClick = (tab) => {
    Ddevice_List_date.clearData()
    const currentTabName = tab.paneName
    Ddevice_List_date.getServerDveiceData(currentTabName)
}

// 表格行样式
const tableRowClassName = ({row, rowIndex}) => {
    if (row.status === '离线') {
        return 'warning-row'
    }
    return ''
}

// 自定义排序方法
const sortStatus = (a, b) => {
    // 在线状态优先
    if (a.status === '在线' && b.status !== '在线') {
        return -1
    } else if (a.status !== '在线' && b.status === '在线') {
        return 1
    } else {
        return a.status.localeCompare(b.status)
    }
}

// 按百分比排序
const sortByPercentage = (a, b) => {
    const aValue = parseFloat(a.cpu_usage || a.memory_usage || a.disk_usage || '0')
    const bValue = parseFloat(b.cpu_usage || b.memory_usage || b.disk_usage || '0')
    return aValue - bValue
}

// 按网络流量排序
const sortByNetworkTraffic = (a, b) => {
    // 简单实现，假设格式为 "1.2 MB/s" 或 "500 KB/s"
    const parseTraffic = (traffic) => {
        if (!traffic) return 0
        const match = traffic.match(/(\d+\.?\d*)\s*(\w+)/)
        if (!match) return 0

        const value = parseFloat(match[1])
        const unit = match[2].toLowerCase()

        // 转换为统一单位 (KB)
        switch(unit) {
            case 'b': return value / 1024
            case 'kb': return value
            case 'mb': return value * 1024
            case 'gb': return value * 1024 * 1024
            default: return value
        }
    }

    return parseTraffic(a.network_traffic) - parseTraffic(b.network_traffic)
}

// 按数字排序
const sortByNumber = (a, b) => {
    const aValue = parseInt(a.network_connections || '0')
    const bValue = parseInt(b.network_connections || '0')
    return aValue - bValue
}

// 获取进度条颜色
const getProgressColor = (percentage) => {
    if (percentage < 50) return '#67c23a' // 绿色
    if (percentage < 80) return '#e6a23c' // 橙色
    return '#f56c6c' // 红色
}

// 格式化MAC地址显示
const formatMac = (mac) => {
    if (!mac) return ''
    // 将MAC地址格式化为每4个字符一组，便于显示
    return mac.replace(/(.{4})/g, '$1 ')
}
</script>

<style module>
/* 主容器 */
.deviceListMain {
    width: 100%;
    height: 100%;
    padding: 20px;
    padding-bottom: 5px;
    color: #fff;
    display: flex;
    flex-direction: column;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.headerBody {
    width: 100%;
    background: #fff;
    padding: 20px;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
    border-radius: 12px;
}


.headerSection {
    margin-bottom: 10px;
}

/* 标签页样式 */
.demoTabs :global(.el-tabs__item:not(.is-active)) {
    color: #c0ccda;
}

/* 容器布局 */
.containerDeviceList {
    height: 100%;
}

/* 标签页样式 */
.demoTabs :global(.el-tabs__item:not(.is-active)) {
    color: #c0ccda;
}

.demoTabs :global(.el-tabs__item.is-active) {
    color: #409eff;
}

.demoTabs :global(.el-tabs__item:hover) {
    color: #409eff;
}

.demoTabs :global(.el-tabs__active-bar) {
    background-color: #409eff;
}

.buttonGroup {
    padding-left: 20px;
}

/* 按钮组样式 */
.buttonGroup :global(.el-button) {
    margin: 0;
    padding-left: 20px;
    background: transparent;
    border: 1px solid #dcdfe6;
    color: #606266;
    transition: all 0.3s ease;
}

.buttonGroup :global(.el-button:hover) {
    background: transparent;
    border-color: #409eff;
    color: #409eff;
}

.buttonActive:global(.el-button) {
    background-color: #409eff !important;
    border-color: #409eff !important;
    color: white !important;
}

.buttonActive:global(.el-button:hover) {
    background-color: #337ecc !important;
    border-color: #337ecc !important;
}

.buttonInactive:global(.el-button) {
    background-color: transparent;
    border-color: #dcdfe6;
    color: #606266;
}






.mainDeviceListDefaultCard {
    /* 让内容区域占据剩余空间 */
    margin-top: 20px;
    display: grid;
    grid-template-columns: repeat(auto-fill, 300px);
    gap: 30px 30px;
    justify-content: center;
    overflow-y: auto;
    background: none;
    border-radius: 12px 12px 0 0;
    background: #fff;
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.08);
}

.deviceListMain :global(.el-main) {
    padding-top: 0px;
}

/* 卡片样式 */
.cardDeviceList {
    width: 300px;
    height: 40%;
    min-height: 530px;
    border-radius: 12px;
    overflow: hidden;
    transition: all 0.3s ease;
    background: linear-gradient(145deg, #ffffff 0%, #f5f7fa 100%);
    position: relative;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
}

.cardDeviceList::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: linear-gradient(90deg, #409EFF 0%, #67C23A 100%);
}

.cardDeviceList:hover {
    transform: translateY(-5px);
    box-shadow: 0 8px 25px rgba(0, 0, 0, 0.12);
}

.cardHeader {
    /* 卡片头部样式 */
    font-weight: bold;
    display: flex;
    justify-content: space-between;
    align-items: center;
    background-color: rgba(64, 158, 255, 0.05);
    padding: 12px 15px;
    border-bottom: 1px solid rgba(64, 158, 255, 0.1);
}

.cardContent {
    display: flex;
    flex-direction: column;
    gap: 15px;
    padding: 15px;
}

.cardInfo {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
    padding: 10px;
    background-color: rgba(245, 247, 250, 0.5);
    border-radius: 8px;
    border: 1px solid rgba(220, 223, 230, 0.3);
}

.infoItem {
    display: flex;
    flex-direction: column;
    gap: 4px;
    padding: 5px;
    border-radius: 4px;
    transition: background-color 0.2s ease;
}

.infoItem:hover {
    background-color: rgba(64, 158, 255, 0.05);
}

.infoLabel {
    font-size: 12px;
    color: #606266;
    font-weight: 500;
    display: flex;
    align-items: center;
}

.infoLabel::before {
    content: '';
    display: inline-block;
    width: 3px;
    height: 12px;
    background-color: #409EFF;
    margin-right: 6px;
    border-radius: 2px;
}

.infoValue {
    font-size: 14px;
    color: #303133;
    word-break: break-all;
    font-weight: 500;
    padding-left: 9px;
}

.cardStats {
    display: flex;
    flex-direction: column;
    gap: 12px;
    padding: 10px;
    background-color: rgba(250, 250, 250, 0.7);
    border-radius: 8px;
    border: 1px solid rgba(220, 223, 230, 0.3);
}

.statItem {
    display: flex;
    flex-direction: column;
    gap: 6px;
    padding: 5px;
    border-radius: 4px;
}

.statLabel {
    font-size: 13px;
    color: #606266;
    font-weight: 500;
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.statValue {
    font-weight: 600;
    color: #409EFF;
    font-size: 14px;
}

/* 列表样式 */
.mainDeviceListDefaultList {
    flex: 1;
    margin-top: 19px;
    overflow: auto;
    border-radius: 12px;
}

.tableDeviceList {
    width: 100%;
    height: 100%;
    background-color: rgba(255, 255, 255, 0.1);
    border-radius: 12px;
}

.tableDeviceList :global(.el-table th) {
    background-color: rgba(255, 255, 255, 0.2) !important;
    color: #fff;
    
}

.tableDeviceList :global(.el-table__header-wrapper) {
    position: sticky !important;
    top: 0 !important;
    z-index: 10 !important;
}

.tableDeviceList :global(.el-table td) {
    color: #fff;
    border-bottom: 1px solid rgba(255, 255, 255, 0.1);
}

.tableDeviceList :global(.el-table--enable-row-hover .el-table__body tr:hover > td) {
    background-color: rgba(255, 255, 255, 0.1);
}

.tableDeviceList :global(.el-table--border::after), 
.tableDeviceList :global(.el-table--group::after), 
.tableDeviceList :global(.el-table::before) {
    background-color: rgba(255, 255, 255, 0.1);
}

.tableDeviceList :global(.el-table--border), 
.tableDeviceList :global(.el-table--group) {
    border: 1px solid rgba(255, 255, 255, 0.1);
}
</style>