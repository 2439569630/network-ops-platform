import { defineStore } from 'pinia'
import { ref } from 'vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import { homeDataStore } from '@/components/home/home/data'

export const useDeviceStore = defineStore('device', () => {
    // 依赖的其他 Store
    const authStore = homeDataStore()

    // 状态
    const data = ref([])
    const loading = ref(false)
    const listError = ref('')
    const dataCard = ref(0) // 0: 卡片视图, 1: 列表视图
    const filterType = ref(0) // 0: 全部, 1: 路由器, 2: 交换机, ...
    const searchQuery = ref('')
    const currentPage = ref(1)
    const pageSize = ref(10)
    
    // WebSocket 相关
    const ws = ref(null)
    const wsStatus = ref('disconnected') // disconnected, connecting, connected
    let reconnectTimer = null
    let reconnectAttempts = 0
    let manualClose = false
    let listLoadingTimer = null
    const LIST_LOADING_TIMEOUT_MS = 5000
    let pingTimer = null
    const PING_INTERVAL_MS = 25000
    let permissionDeniedNotified = false
    let unknownUpdateRefreshTimer = null

    const stopHeartbeat = () => {
        if (pingTimer) {
            clearInterval(pingTimer)
            pingTimer = null
        }
    }

    const scheduleListRefresh = () => {
        if (unknownUpdateRefreshTimer) return
        unknownUpdateRefreshTimer = setTimeout(() => {
            unknownUpdateRefreshTimer = null
            sendGetListCommand()
        }, 300)
    }

    const startHeartbeat = () => {
        stopHeartbeat()
        pingTimer = setInterval(() => {
            if (!ws.value || ws.value.readyState !== WebSocket.OPEN) return
            try {
                ws.value.send(JSON.stringify({ command: 'ping' }))
            } catch {}
        }, PING_INTERVAL_MS)
    }

    const startListLoading = () => {
        listError.value = ''
        loading.value = true
        if (listLoadingTimer) {
            clearTimeout(listLoadingTimer)
            listLoadingTimer = null
        }
        listLoadingTimer = setTimeout(() => {
            if (!loading.value) return
            loading.value = false
            if (!data.value || data.value.length === 0) {
                listError.value = '设备列表加载超时，可尝试重新加载或直接添加设备'
            }
        }, LIST_LOADING_TIMEOUT_MS)
    }

    const stopListLoading = () => {
        loading.value = false
        if (listLoadingTimer) {
            clearTimeout(listLoadingTimer)
            listLoadingTimer = null
        }
    }

    // 计算属性
    const dataLength = () => data.value.length

    const getPaginatedData = () => {
        const start = (currentPage.value - 1) * pageSize.value
        const end = start + pageSize.value
        return data.value.slice(start, end)
    }

    const getdataCardType = () => dataCard.value

    // 操作
    const setdataCardType = (type) => {
        if (type === 0 || type === 1) {
            dataCard.value = type
        }
    }
    
    const setPageSize = (size) => {
        pageSize.value = size
    }

    const setSearchQuery = (query) => {
        searchQuery.value = query
        currentPage.value = 1
        sendGetListCommand()
    }

    const clearData = () => {
        data.value = []
    }

    // 发送 WebSocket 指令
    const sendGetListCommand = () => {
        if (ws.value && ws.value.readyState === WebSocket.OPEN) {
            const command = {
                command: 'get_list',
                type: filterType.value,
                search: searchQuery.value
            }
            ws.value.send(JSON.stringify(command))
            if (!data.value || data.value.length === 0) startListLoading()
        } else if (wsStatus.value !== 'connecting') {
            if (!data.value || data.value.length === 0) startListLoading()
            startRealtime()
        }
    }

    // 刷新数据（供外部调用）
    const refreshData = () => {
        sendGetListCommand()
    }

    // 切换 Tab (Filter Type)
    const setFilterType = (type) => {
        const nextType = Number(type)
        if (!Number.isNaN(nextType) && filterType.value !== nextType) {
            filterType.value = nextType
            currentPage.value = 1
            clearData()
            sendGetListCommand()
        } else if (filterType.value === nextType) {
            // 即使相同也刷新一下
            sendGetListCommand()
        }
    }

    // WebSocket 连接逻辑
    const normalizeHostname = (hostname) => {
        const h = String(hostname || '').trim()
        if (!h || h === '0.0.0.0') return '127.0.0.1'
        return h
    }

    const stopRealtime = () => {
        manualClose = true
        if (reconnectTimer) {
            clearTimeout(reconnectTimer)
            reconnectTimer = null
        }
        if (unknownUpdateRefreshTimer) {
            clearTimeout(unknownUpdateRefreshTimer)
            unknownUpdateRefreshTimer = null
        }
        if (ws.value) {
            ws.value.close()
            ws.value = null
        }
        wsStatus.value = 'disconnected'
        stopListLoading()
        stopHeartbeat()
    }

    const startRealtime = async () => {
        // 防止重复连接
        if (wsStatus.value === 'connected' || wsStatus.value === 'connecting') return

        const session = await authStore.ensureSession()
        if (!session) {
            listError.value = '未登录或会话已失效'
            stopListLoading()
            return
        }
        
        // 简单权限检查 (如果有必要)
        // const hasPerm = authStore.isSuper || (authStore.permissions && authStore.permissions.includes('sys:device:list'))
        // if (!hasPerm) return

        manualClose = false
        wsStatus.value = 'connecting'
        listError.value = ''

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsHost = normalizeHostname(window.location.hostname)
        const wsPort = window.location.port ? `:${window.location.port}` : ''
        const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/user/device/ws/list`

        try {
            const socket = new WebSocket(wsUrl)
            ws.value = socket

            socket.onopen = () => {
                console.log('Device List WebSocket connected')
                wsStatus.value = 'connected'
                reconnectAttempts = 0
                permissionDeniedNotified = false
                listError.value = ''
                startHeartbeat()
                if (!data.value || data.value.length === 0) startListLoading()
                sendGetListCommand()
            }

            socket.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data)
                    if (msg.type === 'list') {
                        data.value = msg.data || []
                        listError.value = ''
                        stopListLoading()
                    } else if (msg.type === 'pong') {
                        return
                    } else if (msg.type === 'update') {
                        const updateItem = msg.data
                        const index = data.value.findIndex(d => d.id === updateItem.id)
                        if (index !== -1) {
                            Object.assign(data.value[index], updateItem)
                        } else {
                            scheduleListRefresh()
                        }
                    }
                } catch (e) {
                    console.error('WS message parse error:', e)
                }
            }

            socket.onerror = (error) => {
                console.error('Device WS error:', error)
                // onerror 之后通常会触发 onclose
            }

            socket.onclose = async (e) => {
                wsStatus.value = 'disconnected'
                ws.value = null
                stopHeartbeat()
                console.log('Device WS closed', e.code, e.reason)

                if (manualClose) return
                stopListLoading()

                // 4003: 无权限
                if (e.code === 4003) {
                    listError.value = '无权限查看设备列表'
                    if (!permissionDeniedNotified) {
                        permissionDeniedNotified = true
                        ElMessage.warning('无权限查看设备列表')
                    }
                    return
                }

                // 4001: Token 失效
                if (e.code === 4001) {
                    listError.value = '会话已失效，正在刷新…'
                    try {
                        await axios.post('/api/v1/auth/refresh')
                        reconnectAttempts = 0
                        startRealtime()
                    } catch (err) {
                        listError.value = '会话已失效，请重新登录'
                        return
                    }
                    return
                }

                // 其他情况（网络错误等）：自动重连
                const delay = Math.min(30000, 1000 * Math.pow(2, reconnectAttempts))
                reconnectAttempts++
                if ((!data.value || data.value.length === 0) && reconnectAttempts >= 2) {
                    listError.value = `设备列表连接不稳定，正在重连（第${reconnectAttempts}次）…`
                }
                console.log(`Reconnecting in ${delay}ms... (Attempt ${reconnectAttempts})`)
                reconnectTimer = setTimeout(() => {
                    startRealtime()
                }, delay)
            }

        } catch (e) {
            console.error('WS create failed:', e)
            wsStatus.value = 'disconnected'
            if (!data.value || data.value.length === 0) {
                listError.value = '无法建立设备列表连接'
            }
            stopListLoading()
            // 尝试重连
            const delay = 5000
            reconnectTimer = setTimeout(() => {
                startRealtime()
            }, delay)
        }
    }

    // 重载设备
    const reloadDevice = async (device) => {
        try {
            if (!device || !device.id) {
                throw new Error('无效的设备信息');
            }
            const response = await axios.post('/api/v1/user/device/reload', { id: device.id });
            if (response.data.code === 200) {
                return true;
            } else {
                throw new Error(response.data.message || '重载失败');
            }
        } catch (error) {
            console.error("重载设备失败：", error);
            ElMessage({
                message: error.response?.data?.message || error.message || '重载设备失败',
                type: 'error'
            });
            return false;
        }
    };

    // 删除设备
    const deleteDevice = async (device) => {
        try {
            let payload = null
            if (device && typeof device === 'object') {
                payload = device.id ? { id: device.id } : { ip: device.ipv4 }
            } else if (typeof device === 'number') {
                payload = { id: device }
            } else if (typeof device === 'string' && device.trim()) {
                const maybeId = Number.parseInt(device, 10)
                payload = Number.isNaN(maybeId) ? { ip: device } : { id: maybeId }
            }

            if (!payload || (!payload.id && !payload.ip)) {
                throw new Error('删除参数无效')
            }
            
            const response = await axios.post('/api/v1/user/device/delete', payload)
            
            if (response.data.code === 200) {
                // 删除成功后，从本地列表中移除
                const index = data.value.findIndex(item => 
                    (device.id && item.id === device.id) || 
                    (!device.id && item.ipv4 === device.ipv4)
                )
                if (index !== -1) {
                    data.value.splice(index, 1)
                }
                return true
            } else {
                throw new Error(response.data.message || '删除失败')
            }
        } catch (error) {
            console.error("删除设备失败：", error)
            ElMessage({
                message: error.response?.data?.message || error.message || '删除设备失败',
                type: 'error'
            })
            return false
        }
    }

    const reloadDevice = async (device) => {
        try {
            const id = typeof device === 'object' ? device.id : device
            if (!id) throw new Error('设备ID无效')
            
            const response = await axios.post(`/api/v1/user/device/reload/${id}`)
            if (response.data.code === 200) {
                return true
            } else {
                throw new Error(response.data.message || '重载指令下发失败')
            }
        } catch (error) {
            console.error("设备重载失败：", error)
            ElMessage({
                message: error.response?.data?.message || error.message || '重载失败',
                type: 'error'
            })
            return false
        }
    }

    // 兼容旧 API 命名 (如果需要，可以直接修改组件调用)
    const getServerDveiceData = (type) => {
        if (type !== undefined) {
            setFilterType(type)
        } else {
            // 只是刷新
            refreshData()
        }
    }

    const resetForLogout = () => {
        stopRealtime()
        data.value = []
        loading.value = false
        listError.value = ''
        dataCard.value = 0
        filterType.value = 0
        searchQuery.value = ''
        currentPage.value = 1
        pageSize.value = 10
        reconnectAttempts = 0
        permissionDeniedNotified = false
    }

    return {
        data,
        loading,
        listError,
        dataCard,
        filterType,
        searchQuery,
        currentPage,
        pageSize,
        dataLength,
        getPaginatedData,
        getdataCardType,
        setdataCardType,
        setSearchQuery,
        clearData,
        refreshData,
        setFilterType,
        setPageSize,
        startRealtime,
        stopRealtime,
        reloadDevice,
        deleteDevice,
        reloadDevice,
        // 兼容旧方法名，建议组件改用 setFilterType 或 refreshData
        getServerDveiceData,
        resetForLogout
    }
})
