import { defineStore } from 'pinia'
import { ref } from 'vue'

// 设备列表数据
export const dveiceDateStore = defineStore('date', () => {
    const date = ref([
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
    ])


    /**
     * 添加数据的函数
     * @param {Object} data - 需要添加的数据对象
     * @returns {void} - 无返回值
     */
    const addData = (data) => {
        console.log(data)
        date.value = data
    }
    /**
     * 清空数据的函数
     * @param {Object} data - 需要清空数据的数据对象
     * @returns {undefined} 该函数没有返回值，直接修改传入的对象
     */
    const clearData = (data) => {
        date.value = []
    }

    return {
        date,
        addData,
        clearData
    }
})