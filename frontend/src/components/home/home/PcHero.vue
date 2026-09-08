<template>
  <div class="hero">
    <div class="hero__bg" />
    <div class="hero__inner">
      <div class="hero__top">
        <div class="identity">
          <el-avatar :size="56" class="identity__avatar" :src="store.form.avatar_url || ''">
            <span>{{ store.initials }}</span>
          </el-avatar>
          <div class="identity__meta">
            <div class="identity__title">
              <span class="identity__greet">{{ store.greeting }}，</span>
              <span class="identity__name">{{ store.displayName }}</span>
            </div>
            <div class="identity__sub">
              <div class="role-tags">
                <el-tag
                  v-for="item in store.roleBadges"
                  :key="item.key"
                  :type="item.type"
                  effect="dark"
                  round
                  size="small"
                >
                  {{ item.label }}
                </el-tag>
              </div>
              <span class="sep" />
              <span>{{ store.nowText }}</span>
              <span class="sep" />
              <span>注册第 {{ store.summary.register_days || 1 }} 天</span>
            </div>
          </div>
        </div>
      </div>

      <div class="kpi-wrap">
        <div class="kpi-grid" :style="gridStyle">
          <div class="kpi">
            <div class="kpi__label">待处理工单</div>
            <div class="kpi__value">{{ store.summary.order_open || 0 }}</div>
          </div>
          <div class="kpi">
            <div class="kpi__label">我的工单</div>
            <div class="kpi__value">{{ store.summary.order_total || 0 }}</div>
          </div>
          <div class="kpi">
            <div class="kpi__label">已完成</div>
            <div class="kpi__value">{{ store.summary.order_done || 0 }}</div>
          </div>
          <div class="kpi" v-if="canShowDeviceStats">
            <div class="kpi__label">我创建的设备</div>
            <div class="kpi__value">{{ store.summary.device_count || 0 }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { homeDataStore } from './data';

const store = homeDataStore();

const canShowDeviceStats = computed(() => {
  return Boolean(store.isSuper) || (Array.isArray(store.permissions) && store.permissions.includes('sys:device:add'));
});

const gridStyle = computed(() => {
  const count = canShowDeviceStats.value ? 4 : 3;
  return {
    gridTemplateColumns: `repeat(${count}, minmax(0, 1fr))`
  };
});
</script>

<style scoped>
.hero {
  position: relative;
  padding: 28px 18px 18px;
}

.hero__bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, #1f6feb 0%, #409eff 35%, #34c759 100%);
  border-radius: 0 0 22px 22px;
  opacity: 0.95;
}

.hero__inner {
  position: relative;
  max-width: 1180px;
  margin: 0 auto;
  padding: 18px;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.28);
  backdrop-filter: blur(14px);
}

.hero__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.identity {
  display: flex;
  align-items: center;
  gap: 14px;
  min-width: 0;
}

.identity__avatar {
  background: rgba(255, 255, 255, 0.22);
  color: #fff;
  font-weight: 700;
  border: 1px solid rgba(255, 255, 255, 0.25);
}

.identity__meta {
  min-width: 0;
}

.identity__title {
  display: flex;
  align-items: baseline;
  gap: 6px;
  color: #fff;
  font-weight: 700;
  letter-spacing: 0.2px;
  font-size: 20px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.identity__greet {
  opacity: 0.95;
}

.identity__name {
  max-width: 320px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.identity__sub {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
  color: rgba(255, 255, 255, 0.92);
  font-size: 13px;
  flex-wrap: wrap;
}

.role-tags {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.sep {
  width: 4px;
  height: 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.75);
  display: inline-block;
}

.kpi-wrap {
  margin-top: 14px;
}

.kpi-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.kpi {
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.14);
  border: 1px solid rgba(255, 255, 255, 0.24);
  padding: 14px 14px 12px;
}

.kpi__label {
  color: rgba(255, 255, 255, 0.88);
  font-size: 12px;
}

.kpi__value {
  margin-top: 6px;
  color: #fff;
  font-weight: 800;
  font-size: 26px;
  line-height: 1.1;
}

@media (max-width: 1100px) {
  .kpi-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }
}

@media (max-width: 720px) {
  .hero__top {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
