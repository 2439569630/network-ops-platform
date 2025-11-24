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
    /* background: linear-gradient(135deg, var(--dark), var(--primary)); */
    overflow: hidden;
}

/* 隐藏全局滚动条 */
html, body {
    overflow: hidden;
    scrollbar-width: none;
    -ms-overflow-style: none;
}

html::-webkit-scrollbar,
body::-webkit-scrollbar {
    display: none;
    width: 0;
}

/* 为所有非根元素启用滚动条 */
div::-webkit-scrollbar {
    width: 8px;
    height: 8px;
}

div::-webkit-scrollbar-track {
    background: #f1f5f9;
    border-radius: 4px;
}

div::-webkit-scrollbar-thumb {
    background: #cbd5e1;
    border-radius: 4px;
    border: none;
}

div::-webkit-scrollbar-thumb:hover {
    background: #94a3b8;
}

div {
    scrollbar-width: thin;
    scrollbar-color: #cbd5e1 #f1f5f9;
}
</style>