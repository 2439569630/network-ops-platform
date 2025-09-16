
<template>
    <div class="app">
        <router-view></router-view>
    </div>
</template>

<style>
* {
    margin: 0;
    padding: 0;
    box-sizing: border-box;
    font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
}
.app {
    width: 100vw;
    height: 100vh;
    background: linear-gradient(135deg, var(--dark), var(--primary));
}
</style>
