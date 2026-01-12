import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'
import Cookies from 'js-cookie'
// 设备列表数据
export const dveiceDateStore = defineStore('data', () => {
    // {
    //     device_name: '日志服务器',
    //     ipv4: '192.168.1.18',
    //     ipv6: '2001:0db8:85a3:0000:0000:8a2e:0370:7353',
    //     mac: '00:1A:2B:3C:4D:71',
    //     status: '在线',
    //     type: '服务器',
    //     location: '无锡',
    //     cpu_usage: '35%',
    //     memory_usage: '55%',
    //     disk_usage: '80%',
    //     network_traffic: '70Mbps',
    //     network_connections: '160'
    // }
    const data = ref([
    ])

    // 数据卡片切换
    const dataCard = ref(0);

    const filterType = ref(0)

    // loading状态
    const loading = ref(false)

    // 分页相关
    const currentPage = ref(1)
    const pageSize = ref(10)

    // 搜索相关
    const searchQuery = ref('')

    /////////////////////////////////////////////
    ///////////////  操作区域 ///////////////////
    ////////////////////////////////////////////
    
    // 发送指令获取数据
    const sendGetListCommand = () => {
        if (ws.value && ws.value.readyState === WebSocket.OPEN) {
            const command = {
                command: 'get_list',
                type: filterType.value,
                search: searchQuery.value
            }
            console.log('Sending command:', command)
            ws.value.send(JSON.stringify(command))
            loading.value = true
        }
    }

    // 设置搜索词并刷新
    const setSearchQuery = (query) => {
        searchQuery.value = query
        currentPage.value = 1 // 重置页码
        sendGetListCommand()
    }
    
    // 强制刷新
    const refreshData = () => {
        sendGetListCommand()
    }

    // 监听 dataCard 变化 (Tab 切换)
    // 注意：Main.vue 里的 handleTabClick 调用了 getServerDveiceData，所以这里可能不需要 watch，或者调整逻辑
    // 现在的 getServerDveiceData 只是初始化连接，如果连接已存在，应该直接发指令






    /**
     * 添加数据的函数
     * @returns {void} - 无返回值
     */
    const addData = (newData) => {
        data.value = newData
    }
    /**
     * 获取数据的函数
     * 该函数用于返回data的value值
     * @returns {any} 返回data.value的值
     */
    const getData = () => {
        return data.value  // 返回data的value属性值
    }

    /**
     * 获取分页数据
     */
    const getPaginatedData = () => {
        const start = (currentPage.value - 1) * pageSize.value
        const end = start + pageSize.value
        return data.value.slice(start, end)
    }

    const dataLength = () => {
        return data.value.length
    }
    /**
     * 清空数据的函数
     * @returns {undefined} 该函数没有返回值，直接修改传入的对象
     */
    const clearData = () => {
        data.value = []
    }


    /**
     * 获取数据卡类型
     * @returns {number} 返回当前数据卡类型的值
     */
    const getdataCardType = () => {
        return dataCard.value
    }
    /**
     * 设置数据卡类型
     * @param {number} type - 数据卡类型，取值范围应为0到1之间
     * @returns {void}
     */
    const setdataCardType = (type) => {
        // 检查type参数是否在0到1的范围内
        if (type <= 1 && type >= 0) {
            // 如果参数有效，则将值赋给dataCard
            dataCard.value = type
        } else {
            console.log('type参数错误')
        }
    }

    // 监听data的变化，决定是否显示加载动画
    // watch(data, (newValue, oldValue) => {
    //     if (newValue.length === 0) {
    //         loading.value = true
    //     } else {
    //         loading.value = false
    //     }
    // })

    // WebSocket 实例
    const ws = ref(null)
    let reconnectAttempted = false
    let listFallbackTimer = null

    const normalizeHostname = (hostname) => {
        const h = String(hostname || '').trim()
        if (!h) return '127.0.0.1'
        if (h === '0.0.0.0') return '127.0.0.1'
        return h
    }

    const fetchListHttp = async () => {
        try {
            const res = await axios.get('/api/v1/user/device/get', { params: { type: filterType.value } })
            const list = Array.isArray(res.data) ? res.data : []
            data.value = list
            loading.value = false
            return list
        } catch (e) {
            loading.value = false
            return []
        }
    }

    // 停止 WebSocket (原停止轮询)
    const stopPolling = () => {
        if (listFallbackTimer) {
            clearTimeout(listFallbackTimer)
            listFallbackTimer = null
        }
        if (ws.value) {
            ws.value.__manualClose = true
            ws.value.close()
            ws.value = null
        }
    }

    const initWebSocket = (urlType = 0) => {
        // 确保先关闭旧连接
        stopPolling()

        const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsHost = normalizeHostname(window.location.hostname)
        const wsPort = window.location.port ? `:${window.location.port}` : ''

        const token = Cookies.get('token')
        
        if (!token) {
            console.error('WebSocket init failed: No token found')
            loading.value = true
            fetchListHttp()
            return
        }

        const wsUrl = `${wsProtocol}//${wsHost}${wsPort}/api/v1/user/device/ws/list?token=${encodeURIComponent(token)}`
        
        console.log('Connecting to WebSocket:', wsUrl)

        try {
            const socket = new WebSocket(wsUrl)
            socket.__manualClose = false
            ws.value = socket

            socket.onopen = () => {
                console.log('Device List WebSocket connected')
                reconnectAttempted = false
                // 连接成功后，立即发送获取列表的指令
                sendGetListCommand()
                if (listFallbackTimer) clearTimeout(listFallbackTimer)
                listFallbackTimer = setTimeout(() => {
                    if (loading.value && (!Array.isArray(data.value) || data.value.length === 0)) {
                        fetchListHttp()
                    }
                }, 2000)
            }

            socket.onmessage = (event) => {
                try {
                    const msg = JSON.parse(event.data)
                    if (msg.type === 'list') {
                        // 收到完整列表
                        console.log('Received device list:', msg.data)
                        data.value = msg.data
                        loading.value = false
                        if (listFallbackTimer) {
                            clearTimeout(listFallbackTimer)
                            listFallbackTimer = null
                        }
                    } else if (msg.type === 'update') {
                        // 收到单个设备更新
                        const updateItem = msg.data
                        const index = data.value.findIndex(d => d.id === updateItem.id)
                        if (index !== -1) {
                            // 仅更新存在的字段
                            Object.assign(data.value[index], updateItem)
                        }
                    }
                } catch (e) {
                    console.error('WebSocket message parse error:', e)
                }
            }

            socket.onerror = (error) => {
                console.error('WebSocket error:', error)
                loading.value = true
                fetchListHttp()
            }
            
            socket.onclose = async (e) => {
                console.log('Device List WebSocket closed', e.code, e.reason)
                if (socket.__manualClose) return
                if (listFallbackTimer) {
                    clearTimeout(listFallbackTimer)
                    listFallbackTimer = null
                }

                const closeCode = Number(e?.code || 0)
                if (closeCode === 4003) {
                    loading.value = false
                    ElMessage.warning('无权限查看设备列表')
                    return
                }
                if (closeCode !== 4001) return
                if (reconnectAttempted) return
                reconnectAttempted = true
                try {
                    const res = await axios.post('/api/v1/auth/refresh')
                    const nextToken = res?.data?.token
                    if (nextToken) Cookies.set('token', nextToken, { sameSite: 'lax' })
                    initWebSocket(urlType)
                } catch (err) {
                    loading.value = false
                    ElMessage.error('登录已失效，请重新登录')
                }
            }
        } catch (e) {
             console.error('WebSocket creation failed:', e)
             loading.value = true
             fetchListHttp()
        }
    }

    const getServerDveiceData = async (urlType = 0) => {
        try {
            const nextType = Number.parseInt(String(urlType ?? 0), 10)
            if (!Number.isNaN(nextType)) {
                filterType.value = nextType
            }
            
            // 初始化 WebSocket 连接 (如果已连接，则复用)
            if (!ws.value || ws.value.readyState !== WebSocket.OPEN) {
                currentPage.value = 1
                loading.value = true
                initWebSocket(urlType)
            } else {
                // 已连接，直接发送指令
                // 这里可能需要先更新内部的 type 状态，以便 sendGetListCommand 使用正确的 type
                // 但目前的 sendGetListCommand 使用 dataCard.value。
                // 暂时假设调用者会先设置 dataCard
                sendGetListCommand()
            }
            
        } catch (error) {
            console.error("启动设备列表获取失败：", error)
            loading.value = false
        }
    }

    // 保留 fetchData 供手动刷新或其他用途（如果需要）
    const fetchData = async (urlType, isSilent = false) => {
         // ... implementation if needed, but WS handles it now
    }

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

    return {
        data, // 导出 data
        getData,
        addData,
        loading,
        dataCard,
        filterType,
        clearData,
        setdataCardType,
        getdataCardType,
        getServerDveiceData,
        dataLength,
        stopPolling, // 导出停止方法
        currentPage,
        pageSize,
        getPaginatedData,
        deleteDevice, // 导出删除方法
        setSearchQuery,
        refreshData
    }
})
