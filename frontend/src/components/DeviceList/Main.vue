<template>
    <div :class="$style.container">
        <!-- 顶部控制栏 -->
        <div :class="$style.header">
            <div :class="$style.controls">
                <el-button-group>
                    <el-button :type="isCardView ? 'primary' : 'default'" @click="setCardView(true)" :icon="Grid" />
                    <el-button :type="!isCardView ? 'primary' : 'default'" @click="setCardView(false)" :icon="List" />
                </el-button-group>
            </div>
            
            <div :class="$style.tabs" v-if="isCardView">
                <el-tabs v-model="activeTab" @tab-click="handleTabClick">
                    <el-tab-pane label="全部设备" name="0"></el-tab-pane>
                    <el-tab-pane label="路由器" name="1"></el-tab-pane>
                    <el-tab-pane label="交换机" name="2"></el-tab-pane>
                    <el-tab-pane label="防火墙" name="3"></el-tab-pane>
                    <el-tab-pane label="服务器" name="4"></el-tab-pane>
                </el-tabs>
            </div>
        </div>

        <!-- 内容区域 -->
        <div :class="$style.content">
            <!-- 卡片视图 -->
            <div v-if="isCardView" :class="$style.cardGrid">
                <div v-for="(item, index) in deviceList" :key="index" :class="$style.card">
                    <div :class="[$style.statusStrip, $style[getDeviceStatusTagType(item)]]"></div>
                    <div :class="$style.cardContent">
                        <div :class="$style.cardTop">
                            <div :class="$style.cardHeaderRow">
                                <span :class="$style.deviceName" :title="item.device_name">{{ item.device_name }}</span>
                                <el-tag :type="getDeviceStatusTagType(item)" size="small" effect="light" round class="status-tag">
                                    {{ getDeviceStatusText(item, nowTick) }}
                                </el-tag>
                            </div>
                            <div :class="$style.cardSubHeader">
                                <el-icon><Link /></el-icon>
                                <span>{{ item.ipv4 }}</span>
                            </div>
                        </div>

                        <div :class="$style.infoSection">
                            <div :class="$style.infoRow">
                                <el-icon :class="$style.icon"><Monitor /></el-icon>
                                <span :class="$style.infoText">{{ item.type }}</span>
                            </div>
                            <div :class="$style.infoRow">
                                <el-icon :class="$style.icon"><Location /></el-icon>
                                <span :class="$style.infoText">{{ item.location }}</span>
                            </div>
                            <div :class="$style.infoRow">
                                <el-icon :class="$style.icon"><Odometer /></el-icon>
                                <span :class="$style.infoText" :title="item.mac">{{ formatMac(item.mac) }}</span>
                            </div>
                        </div>

                        <div :class="$style.resourceSection">
                            <div :class="$style.resItem">
                                <div :class="$style.resHeader">
                                    <span :class="$style.resLabel">CPU</span>
                                    <span :class="$style.resValue">{{ item.cpu_usage || '0%' }}</span>
                                </div>
                                <el-progress :percentage="parseFloat(item.cpu_usage || 0)" :color="getProgressColor" :stroke-width="4" :show-text="false" />
                            </div>
                            <div :class="$style.resItem">
                                <div :class="$style.resHeader">
                                    <span :class="$style.resLabel">MEM</span>
                                    <span :class="$style.resValue">{{ item.memory_usage || '0%' }}</span>
                                </div>
                                <el-progress :percentage="parseFloat(item.memory_usage || 0)" :color="getProgressColor" :stroke-width="4" :show-text="false" />
                            </div>
                            <div :class="$style.resItem">
                                <div :class="$style.resHeader">
                                    <span :class="$style.resLabel">DISK</span>
                                    <span :class="$style.resValue">{{ item.disk_usage || '0%' }}</span>
                                </div>
                                <el-progress :percentage="parseFloat(item.disk_usage || 0)" :color="getProgressColor" :stroke-width="4" :show-text="false" />
                            </div>
                        </div>

                        <div :class="$style.cardFooter">
                            <el-tooltip content="查看详情" placement="top" :show-after="500">
                                <el-button text circle type="primary" :icon="View" @click="showDeviceDetail(item)" />
                            </el-tooltip>
                            <el-tooltip content="SSH连接" placement="top" :show-after="500" v-if="canSsh">
                                <el-button text circle type="success" :icon="Connection" @click="connectSSH(item)" :disabled="!isSshEnabled(item)" />
                            </el-tooltip>
                            <el-tooltip content="重载监控" placement="top" :show-after="500" v-if="canEdit">
                                <el-button text circle type="warning" :icon="Refresh" @click="handleReload(item)" />
                            </el-tooltip>
                            <el-tooltip content="删除设备" placement="top" :show-after="500" v-if="canDelete">
                                <el-button text circle type="danger" :icon="Delete" @click="handleDelete(item)" />
                            </el-tooltip>

                        </div>
                    </div>
                </div>
            </div>

            <!-- 列表视图 -->
            <div v-else :class="$style.tableWrapper">
                <el-table :data="deviceList" style="width: 100%; height: 100%" :header-cell-style="{background:'#f5f7fa', color:'#606266', fontWeight: '600'}">
                    <el-table-column prop="device_name" label="设备名称" min-width="180" sortable fixed>
                        <template #default="{ row }">
                            <div :class="$style.deviceNameCell">
                                <div :class="[$style.statusDot, $style[getDeviceStatusTagType(row)]]"></div>
                                <span :title="row.device_name" style="font-weight: 600; color: #303133;">{{ row.device_name }}</span>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="ipv4" label="IPv4" min-width="140" sortable>
                         <template #default="{ row }">
                            <span style="font-family: monospace;">{{ row.ipv4 }}</span>
                        </template>
                    </el-table-column>
                    <el-table-column prop="mac" label="MAC地址" min-width="160">
                        <template #default="{ row }">
                            <span style="font-family: monospace; color: #909399;">{{ formatMac(row.mac) }}</span>
                        </template>
                    </el-table-column>
                    <el-table-column prop="status" label="状态" min-width="180" sortable>
                        <template #default="{ row }">
                            <el-tag :type="getDeviceStatusTagType(row)" size="small" effect="light" round>
                                {{ getDeviceStatusText(row, nowTick) }}
                            </el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column prop="type" label="类型" width="120" sortable />
                    <el-table-column prop="location" label="位置" width="120" />
                    <el-table-column prop="cpu_usage" label="CPU" width="160" sortable>
                        <template #default="{ row }">
                            <div :class="$style.resourceCell">
                                <el-progress :percentage="parseFloat(row.cpu_usage || 0)" :color="getProgressColor" :stroke-width="6" :show-text="false" style="width: 80px" />
                                <span :class="$style.resValueText">{{ row.cpu_usage || '0%' }}</span>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="memory_usage" label="内存" width="160" sortable>
                        <template #default="{ row }">
                            <div :class="$style.resourceCell">
                                <el-progress :percentage="parseFloat(row.memory_usage || 0)" :color="getProgressColor" :stroke-width="6" :show-text="false" style="width: 80px" />
                                <span :class="$style.resValueText">{{ row.memory_usage || '0%' }}</span>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column prop="disk_usage" label="磁盘" width="160" sortable>
                        <template #default="{ row }">
                            <div :class="$style.resourceCell">
                                <el-progress :percentage="parseFloat(row.disk_usage || 0)" :color="getProgressColor" :stroke-width="6" :show-text="false" style="width: 80px" />
                                <span :class="$style.resValueText">{{ row.disk_usage || '0%' }}</span>
                            </div>
                        </template>
                    </el-table-column>
                    <el-table-column label="操作" width="150" fixed="right" align="center">
                        <template #default="{ row }">
                            <div :class="$style.actionButtons">
                                <el-tooltip content="查看详情" placement="top" :show-after="500">
                                    <el-button text circle type="primary" :icon="View" size="small" @click="showDeviceDetail(row)" />
                                </el-tooltip>
                                <el-tooltip content="SSH连接" placement="top" :show-after="500" v-if="canSsh">
                                    <el-button text circle type="success" :icon="Connection" size="small" @click="connectSSH(row)" :disabled="!isSshEnabled(row)" />
                                </el-tooltip>
                                <el-tooltip content="重载监控" placement="top" :show-after="500" v-if="canEdit">
                                    <el-button text circle type="warning" :icon="Refresh" size="small" @click="handleReload(row)" />
                                </el-tooltip>
                                <el-tooltip content="删除设备" placement="top" :show-after="500" v-if="canDelete">
                                    <el-button text circle type="danger" :icon="Delete" size="small" @click="handleDelete(row)" />
                                </el-tooltip>
                                <el-tooltip content="重载设备" placement="top" :show-after="500">
                                    <el-button text circle type="warning" :icon="Refresh" size="small" @click="handleReload(row)" />
                                </el-tooltip>
                            </div>
                        </template>
                    </el-table-column>
                </el-table>
            </div>
        </div>
    </div>
</template>

<script setup>
import { ref, computed, onBeforeUnmount, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { Grid, List, View, Connection, Delete, Location, Monitor, Link, Odometer, Refresh } from '@element-plus/icons-vue';
import { useDeviceStore } from './store';
import { ElMessageBox, ElMessage } from 'element-plus';
import { homeDataStore } from '@/components/home/home/data'
import { getDeviceStatusTagType, getDeviceStatusText, isSshEnabled } from './deviceStatus'

const store = useDeviceStore();
const router = useRouter();
const authStore = homeDataStore()
const activeTab = ref('0');
const nowTick = ref(Date.now())
let nowTimer = null

// 计算属性和状态
const isCardView = computed(() => store.getdataCardType() === 0);
const deviceList = computed(() => store.getPaginatedData());
const canSsh = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:ssh:connect')))
const canEdit = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:edit')))
const canDelete = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:device:del')))

// 方法
const setCardView = (isCard) => {
    store.setdataCardType(isCard ? 0 : 1);
};

const handleTabClick = (tab) => {
    store.clearData();
    store.getServerDveiceData(tab.paneName);
};

const connectSSH = (item) => {
    if (!canSsh.value) return
    if (item.ipv4) {
        let port = 22
        try {
            port = parseInt(String(item.ssh_port || item.port || 22), 10)
        } catch (e) {
            port = 22
        }
        if (!Number.isFinite(port) || port <= 0 || port > 65535) port = 22
        router.push({
            name: 'ssh-connection',
            params: { ip: item.ipv4 },
            query: { port: String(port) }
        });
    }
};

const showDeviceDetail = (item) => {
    const id = item?.id
    if (id) {
        router.push({
            name: 'device-detail',
            params: { id: id }
        });
    } else {
        ElMessage.warning('设备 ID 无效')
    }
};

const formatMac = (mac) => {
    if (!mac) return '';
    return mac.replace(/(.{4})/g, '$1 ').trim();
};

const getProgressColor = (percentage) => {
    if (percentage < 50) return '#67c23a';
    if (percentage < 80) return '#e6a23c';
    return '#f56c6c';
};



const handleDelete = (item) => {
    ElMessageBox.confirm(
        '确定要删除该设备吗？删除后将移入回收站',
        '警告',
        {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
        }
    )
        .then(async () => {
            const success = await store.deleteDevice(item);
            if (success) {
                ElMessage({
                    type: 'success',
                    message: '删除成功',
                });
                store.refreshData(); // 刷新列表
            } else {
                ElMessage({
                    type: 'error',
                    message: '删除失败',
                });
            }
        })
        .catch(() => {
            // 取消
        });
};

const handleReload = (item) => {
    ElMessageBox.confirm(
        '确定要重载该设备吗？这将重启设备的监控进程。',
        '提示',
        {
            confirmButtonText: '确定',
            cancelButtonText: '取消',
            type: 'warning',
        }
    )
    .then(async () => {
        const success = await store.reloadDevice(item);
        if (success) {
            ElMessage({
                type: 'success',
                message: '重载指令已发送',
            });
        } else {
            ElMessage({
                type: 'error',
                message: '重载失败',
            });
        }
    })
    .catch(() => {
        // 取消
    });
};

// 生命周期
onMounted(() => {
    authStore.syncAuthFromToken()
    authStore.fetchPermissions()
    nowTimer = window.setInterval(() => {
        nowTick.value = Date.now()
    }, 1000)
})

onBeforeUnmount(() => {
    if (nowTimer) {
        clearInterval(nowTimer)
        nowTimer = null
    }
    store.stopRealtime();
});
</script>

<style module>
.container {
    height: 100%;
    display: flex;
    flex-direction: column;
    background-color: #f0f2f5;
    padding: 20px;
    box-sizing: border-box;
    overflow: hidden;
}

.header {
    background: #fff;
    padding: 15px 20px;
    border-radius: 8px;
    display: flex;
    align-items: center;
    gap: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
    flex-shrink: 0;
    margin-bottom: 20px;
}

.tabs {
    flex: 1;
    overflow: hidden;
}

/* 覆盖 Element Plus Tabs 底部边距 */
.tabs :global(.el-tabs__header) {
    margin-bottom: 0;
}

.content {
    flex: 1;
    overflow: hidden;
    position: relative;
    border-radius: 8px;
}

/* 卡片视图网格 */
.cardGrid {
    height: 100%;
    overflow-y: auto;
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
    align-content: flex-start;
    gap: 20px;
    padding-bottom: 20px;
}

.card {
    background: #fff;
    border-radius: 12px;
    position: relative;
    box-shadow: 0 2px 12px 0 rgba(0, 0, 0, 0.05);
    transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
    border: 1px solid #ebeef5;
    overflow: hidden;
    display: flex;
    flex-direction: column;
}

.card:hover {
    transform: translateY(-4px);
    box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

/* 状态颜色通用类 */
.success { background-color: #67c23a !important; }
.warning { background-color: #e6a23c !important; }
.danger { background-color: #f56c6c !important; }
.info { background-color: #909399 !important; }

.statusStrip {
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 4px;
    background: #909399;
}

/* 移除旧的组合选择器，使用通用类 */
/* .statusStrip.success { background: #67c23a; } */
/* ... */

.cardContent {
    padding: 20px;
    display: flex;
    flex-direction: column;
    height: 100%;
    box-sizing: border-box;
}

.cardTop {
    margin-bottom: 16px;
}

.cardHeaderRow {
    display: flex;
    align-items: center;
    margin-bottom: 8px;
}

.deviceName {
    font-weight: 600;
    font-size: 16px;
    color: #303133;
    flex: 1;
    min-width: 0;
    margin-right: 8px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

/* .cardStatusRow removed */

.cardHeaderRow :global(.el-tag) {
    white-space: normal;
    height: auto;
    padding: 2px 8px;
    line-height: 1.4;
    text-align: left;
    max-width: 100%;
    flex-shrink: 0;
}

.cardSubHeader {
    display: flex;
    align-items: center;
    gap: 6px;
    color: #909399;
    font-size: 13px;
}

.infoSection {
    display: flex;
    flex-direction: column;
    gap: 10px;
    margin-bottom: 20px;
    background: #f8f9fa;
    padding: 12px;
    border-radius: 8px;
}

.infoRow {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 13px;
    color: #606266;
    line-height: 1.2;
}

.icon {
    font-size: 14px;
    color: #909399;
    flex-shrink: 0;
}

.infoText {
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.resourceSection {
    margin-top: auto;
    display: flex;
    flex-direction: column;
    gap: 8px;
    margin-bottom: 16px;
    padding: 0 4px;
}

.resItem {
    display: flex;
    flex-direction: column;
    gap: 6px;
    font-size: 13px;
    color: #606266;
}

.resHeader {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.resLabel {
    color: #909399;
    font-weight: 500;
}

.resValue {
    font-family: monospace;
    font-weight: 600;
    color: #303133;
}

.cardFooter {
    border-top: 1px solid #f0f2f5;
    padding-top: 12px;
    display: flex;
    justify-content: flex-end;
    gap: 8px;
}

.cardFooter :global(.el-button) {
    margin-left: 0 !important;
}

/* 列表视图容器 */
.tableWrapper {
    height: 100%;
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}

.deviceNameCell {
    display: flex;
    align-items: center;
    gap: 10px;
}

.statusDot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex-shrink: 0;
}

.resourceCell {
    display: flex;
    align-items: center;
    gap: 8px;
}

.resValueText {
    font-family: monospace;
    font-size: 12px;
    color: #606266;
    width: 35px;
    text-align: right;
}

.actionButtons {
    display: flex;
    justify-content: center;
    gap: 4px;
}
</style>
