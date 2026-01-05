<template>
    <div class="ssh-wrapper">
        <SSHConnection />
    </div>
</template>

<script setup>
import SSHConnection from './SSHConnection.vue';
</script>

<style scoped>
.ssh-wrapper {
    width: 100%;
    height: 100%;
    overflow: hidden;
}
</style>
