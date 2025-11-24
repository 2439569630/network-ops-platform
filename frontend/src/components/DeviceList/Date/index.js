import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import axios from '@/axios/axios'
import { ElMessage } from 'element-plus'

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

    // loading状态
    const loading = ref(false)




    /////////////////////////////////////////////
    ///////////////  操作区域 ///////////////////
    ////////////////////////////////////////////





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
    watch(data, (newValue, oldValue) => {
        if (newValue.length === 0) {
            loading.value = true
        } else {
            loading.value = false
        }
    })



    const getServerDveiceData = async (urlType = 0) => {
        try {
            const timeout = 10000 // 设置超时时间为10秒
            // 构建url
            const url = `/user/device/get?type=${urlType}`
            console.log(urlType)

            // 添加超时控制
            const response = await Promise.race([
                axios.get(url),
                new Promise((_, reject) =>
                    setTimeout(() => reject(new Error('请求超时')), timeout)
                )
            ])

            if (response.data) {
                addData(response.data)
                return response.data
            }
        } catch (error) {
            console.error("获取设备列表数据失败：", error)

            const errorMessage = error.message === '请求超时'
                ? '请求超时，请检查网络连接'
                : error.response?.data?.message || error.message || '获取设备数据失败'

            ElMessage({
                message: errorMessage,
                type: 'error'
            })

            throw error
        }
    }











    return {
        getData,
        addData,
        loading,
        dataCard,
        clearData,
        setdataCardType,
        getdataCardType,
        getServerDveiceData,
        dataLength,

    }
})