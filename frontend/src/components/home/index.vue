<template >
  <div class="common-layout">
    <el-container>
      <el-container class="container">
        <el-aside class="aside"> <LEFT /> </el-aside>
        <el-main class="main"> <RouterView></RouterView> </el-main>
      </el-container>
    </el-container>
  </div>
</template>
<script setup>
import heada from './header.vue';
import DATE from './home/home.vue'
import LEFT from './left/left.vue'


</script>
<style scoped>
.common-layout{
    width: 100vw;
    height: 100vh;
    color: #fff;
}

.aside {
    width: 15vw;
    height: 100vh;
    /* background: rgba(45, 55, 72, 0.6); */
}
.main {
    width: 80vw;
    /* background: rgba(45, 55, 72, 0.6); */
    height: 100vh;

}

</style>