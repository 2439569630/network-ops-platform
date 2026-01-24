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
                <el-card v-for="(item, index) in deviceList" :key="index" :class="$style.card" shadow="hover">
                    <template #header>
                        <div :class="$style.cardHeader">
                            <span :class="$style.deviceName" :title="item.device_name">{{ item.device_name }}</span>
                            <el-tag :type="getDeviceStatusTagType(item)" size="small" effect="dark">
                                {{ getDeviceStatusText(item) }}
                            </el-tag>
                        </div>
                    </template>
                    
                    <div :class="$style.cardBody">
                        <div :class="$style.infoGrid">
                            <div :class="$style.infoItem">
                                <span :class="$style.label">设备类型</span>
                                <span :class="$style.value">{{ item.type }}</span>
                            </div>
                            <div :class="$style.infoItem">
                                <span :class="$style.label">位置</span>
                                <span :class="$style.value">{{ item.location }}</span>
                            </div>
                            <div :class="$style.infoItem">
                                <span :class="$style.label">IPv4</span>
                                <span :class="$style.value">{{ item.ipv4 }}</span>
                            </div>
                            <div :class="$style.infoItem">
                                <span :class="$style.label">MAC</span>
                                <span :class="$style.value" :title="item.mac">{{ formatMac(item.mac) }}</span>
                            </div>
                        </div>

                        <div :class="$style.statsList">
                            <div :class="$style.statItem">
                                <div :class="$style.statHeader">
                                    <span>CPU</span>
                                    <span :class="$style.statValue">{{ item.cpu_usage || '0' }}</span>
                                </div>
                                <el-progress :percentage="parseFloat(item.cpu_usage || 0)" :color="getProgressColor" :show-text="false" :stroke-width="6" />
                            </div>
                            <div :class="$style.statItem">
                                <div :class="$style.statHeader">
                                    <span>内存</span>
                                    <span :class="$style.statValue">{{ item.memory_usage || '0' }}</span>
                                </div>
                                <el-progress :percentage="parseFloat(item.memory_usage || 0)" :color="getProgressColor" :show-text="false" :stroke-width="6" />
                            </div>
                            <div :class="$style.statItem">
                                <div :class="$style.statHeader">
                                    <span>磁盘</span>
                                    <span :class="$style.statValue">{{ item.disk_usage || '0' }}</span>
                                </div>
                                <el-progress :percentage="parseFloat(item.disk_usage || 0)" :color="getProgressColor" :show-text="false" :stroke-width="6" />
                            </div>
                        </div>

                        <div :class="$style.actions">
                            <el-button type="primary" size="small" :icon="View" @click="showDeviceDetail(item)">详情</el-button>
                            <el-button v-if="canSsh" type="success" size="small" :icon="Connection" @click="connectSSH(item)" :disabled="!isSshEnabled(item)">SSH</el-button>
                            <el-button v-if="canDelete" type="danger" size="small" :icon="Delete" @click="handleDelete(item)">删除</el-button>
                        </div>
                    </div>
                </el-card>
            </div>

            <!-- 列表视图 -->
            <div v-else :class="$style.tableWrapper">
                <el-table :data="deviceList" style="width: 100%; height: 100%" :header-cell-style="{background:'#f5f7fa', color:'#606266'}">
                    <el-table-column prop="device_name" label="设备名称" min-width="150" sortable />
                    <el-table-column prop="ipv4" label="IPv4" min-width="140" sortable />
                    <el-table-column prop="mac" label="MAC地址" min-width="160" />
                    <el-table-column prop="status" label="状态" width="100" sortable>
                        <template #default="{ row }">
                            <el-tag :type="getDeviceStatusTagType(row)">{{ getDeviceStatusText(row) }}</el-tag>
                        </template>
                    </el-table-column>
                    <el-table-column prop="type" label="类型" width="120" sortable />
                    <el-table-column prop="location" label="位置" width="120" />
                    <el-table-column prop="cpu_usage" label="CPU" width="100" sortable />
                    <el-table-column prop="memory_usage" label="内存" width="100" sortable />
                    <el-table-column label="操作" width="200" fixed="right">
                        <template #default="{ row }">
                            <el-button link type="primary" size="small" @click="showDeviceDetail(row)">详情</el-button>
                            <el-button v-if="canSsh" link type="success" size="small" @click="connectSSH(row)" :disabled="!isSshEnabled(row)">SSH</el-button>
                            <el-button v-if="canDelete" link type="danger" size="small" @click="handleDelete(row)">删除</el-button>
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
import { Grid, List, View, Connection, Delete } from '@element-plus/icons-vue';
import { useDeviceStore } from './store';
import { ElMessageBox, ElMessage } from 'element-plus';
import { homeDataStore } from '@/components/home/home/data'
import { getDeviceStatusTagType, getDeviceStatusText, isSshEnabled } from './deviceStatus'

const store = useDeviceStore();
const router = useRouter();
const authStore = homeDataStore()
const activeTab = ref('0');

// 计算属性和状态
const isCardView = computed(() => store.getdataCardType() === 0);
const deviceList = computed(() => store.getPaginatedData());
const canSsh = computed(() => Boolean(authStore.isSuper) || (Array.isArray(authStore.permissions) && authStore.permissions.includes('sys:ssh:connect')))
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
        router.push({
            name: 'ssh-connection',
            params: { ip: item.ipv4 }
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

// 生命周期
onMounted(() => {
    authStore.syncAuthFromToken()
    authStore.fetchPermissions()
})

onBeforeUnmount(() => {
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
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    gap: 20px;
    padding-bottom: 20px; /* 底部留白 */
}

.card {
    width: 300px;
    display: flex;
    flex-direction: column;
    border: none;
    transition: transform 0.2s, box-shadow 0.2s;
}

.card:hover {
    transform: translateY(-4px);
    box-shadow: 0 4px 12px rgba(0,0,0,0.1);
}

.cardHeader {
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.deviceName {
    font-weight: 600;
    font-size: 16px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 180px;
}

.cardBody {
    display: flex;
    flex-direction: column;
    gap: 15px;
}

.infoGrid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    font-size: 13px;
    background: #f8f9fa;
    padding: 10px;
    border-radius: 6px;
}

.infoItem {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.label {
    color: #909399;
    font-size: 12px;
}

.value {
    color: #303133;
    font-weight: 500;
    word-break: break-all;
}

.statsList {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.statItem {
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.statHeader {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    color: #606266;
}

.statValue {
    font-weight: 600;
    color: #409eff;
}

.actions {
    display: flex;
    justify-content: space-between;
    margin-top: 5px;
}

.actions button {
    width: 48%;
}

/* 列表视图容器 */
.tableWrapper {
    height: 100%;
    background: #fff;
    border-radius: 8px;
    padding: 20px;
    box-shadow: 0 1px 4px rgba(0,0,0,0.05);
}
</style>
