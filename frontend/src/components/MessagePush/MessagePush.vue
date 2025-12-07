<template>
  <div class="message-push-container">
    <h1>消息推送系统</h1>
    <nav class="message-options">
      <router-link to="/message/serial" class="nav-link">串行推送</router-link>
      <router-link to="/message/parallel" class="nav-link">并行推送</router-link>
    </nav>
    <router-view></router-view>
  </div>
</template>

<script setup>
// 可以根据需要添加组件逻辑
</script>

<style scoped>
.message-push-container {
  padding: 20px;
  font-family: 'Arial', sans-serif;
}

h1 {
  color: #333;
  margin-bottom: 20px;
}

.message-options {
  margin-bottom: 20px;
}

.nav-link {
  margin-right: 15px;
  padding: 10px 15px;
  text-decoration: none;
  color: #007bff;
  border: 1px solid #007bff;
  border-radius: 5px;
  transition: all 0.3s ease;
}

.nav-link:hover {
  background-color: #007bff;
  color: white;
}

.nav-link.router-link-active {
  background-color: #007bff;
  color: white;
  border-color: #007bff;
}
</style>
