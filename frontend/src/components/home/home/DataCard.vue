<template v-once>
    <div class="data-card">
        <!--  网络概览 -->
        <div class="overview">
            <overview />
        </div>
        <!-- 网络拓扑视图 -->
        <div class="topology">
            <topology />
        </div>
        <!--  实时告警 -->
        <div class="alerts">
            <alerts />
        </div>
        <!-- 设备状态 -->
        <div class="device-status">
            <deviceStatus />
        </div>
        <!-- 性能监控 -->
        <div class="performance-monitoring">
            <performanceMonitoring />
        </div>
        <!-- 自动化任务 -->
        <div class="automation-tasks">
            <automationTasks />
        </div>

    </div>
</template>
<script setup>
import overview from './Card/overview.vue';
import topology from './Card/topology.vue';
import alerts from './Card/alerts.vue';
import deviceStatus from './Card/device-status.vue';
import performanceMonitoring from './Card/performance-monitoring.vue'
import automationTasks from './Card/automation-tasks.vue'
</script>

<style scoped>
.data-card {
    width: 100%;
    height: 100%;
    border-radius: 10px;
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 20px;
}

.data-card > div {
    width: 100%;
    height: 100%;
    background: rgba(45, 55, 72, 0.6);
    border-radius: 10px;
    overflow: hidden;
    box-shadow: 0 4px 15px rgba(0, 0, 0, 0.15);
    /* transition: transform 0.3s, box-shadow 0.3s; */
    backdrop-filter: blur(10px);
    border: 1px solid rgba(255, 255, 255, 0.1);
}


/* .data-card > div:hover {
    transform: translateY(-5px);
    box-shadow: 0 8px 20px rgba(0, 0, 0, 0.25);
} */


.overview {
    grid-column: span 3;
}

.topology {
    grid-column: span 6;
}

.alerts {
    grid-column: span 3;
}

.device-status {
    grid-column: span 4;
}

.performance-monitoring {
    grid-column: span 4;
}

.automation-tasks {
    grid-column: span 4;
}


/* 中等屏幕 */
@media (max-width: 1199px) {
    .overview {
        grid-column: span 6;
    }

    .topology {
        grid-column: span 6;
    }

    .alerts {
        grid-column: span 6;
    }

    .device-status {
        grid-column: span 6;
    }

    .performance-monitoring {
        grid-column: span 6;
    }

    .automation-tasks {
        grid-column: span 6;
    }
}

/* 小屏幕 */
@media (max-width: 991px) {
    .data-card {
        gap: 15px;
    }

    .overview {
        grid-column: span 12;
    }

    .topology {
        grid-column: span 12;
    }

    .alerts {
        grid-column: span 12;
    }

    .device-status {
        grid-column: span 12;
    }

    .performance-monitoring {
        grid-column: span 12;
    }

    .automation-tasks {
        grid-column: span 12;
    }
}

/* 超小屏幕 */
@media (max-width: 767px) {
    .data-card {
        grid-template-columns: 1fr;
        gap: 15px;
    }

    .data-card div {
        grid-column: span 1 !important;
    }
}
</style>