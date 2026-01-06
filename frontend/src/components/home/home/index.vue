<template>
  <div class="pc">
    <PcHero />

    <div class="content">
      <el-row :gutter="16">
        <el-col :lg="6" :md="24" :sm="24" :xs="24">
          <PcNav :active-page="activePage" @select="setPage" />
        </el-col>

        <el-col :lg="18" :md="24" :sm="24" :xs="24">
          <component :is="pageComponent" />
        </el-col>
      </el-row>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { homeDataStore } from './data';
import PcEmail from './PcEmail.vue';
import PcHero from './PcHero.vue';
import PcNav from './PcNav.vue';
import PcNotification from './PcNotification.vue';
import PcOverview from './PcOverview.vue';
import PcProfile from './PcProfile.vue';
import PcSecurity from './PcSecurity.vue';

const router = useRouter();
const route = useRoute();
const store = homeDataStore();

const activePage = computed(() => {
  const p = String(route.query.page || 'overview');
  const allow = ['overview', 'profile', 'email', 'security', 'notification'];
  return allow.includes(p) ? p : 'overview';
});

const setPage = (key) => {
  router.replace({ query: { ...route.query, page: key } });
};

const pageComponent = computed(() => {
  if (activePage.value === 'profile') return PcProfile;
  if (activePage.value === 'email') return PcEmail;
  if (activePage.value === 'security') return PcSecurity;
  if (activePage.value === 'notification') return PcNotification;
  return PcOverview;
});

onMounted(() => {
  store.startClock();
  store.startPolling(() => activePage.value);
});

onBeforeUnmount(() => {
  store.stopClock();
  store.stopEmailCooldown();
  store.stopPolling();
});
</script>

<style scoped>
.pc {
  min-height: 100%;
  background: radial-gradient(1200px 600px at 20% 0%, rgba(64, 158, 255, 0.20), transparent 60%),
    radial-gradient(900px 500px at 90% 20%, rgba(103, 194, 58, 0.16), transparent 55%),
    #f6f8fb;
}

.content {
  max-width: 1180px;
  margin: -18px auto 0;
  padding: 0 18px 28px;
}
</style>
