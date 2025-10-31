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
    width: 10px;
    height: 10px;
}

div::-webkit-scrollbar-track {
    background: #2d3748;
    border-radius: 5px;
}

div::-webkit-scrollbar-thumb {
    background: #4a5568;
    border-radius: 5px;
    border: 2px solid #2d3748;
}

div::-webkit-scrollbar-thumb:hover {
    background: #718096;
}

div {
    scrollbar-width: thin;
    scrollbar-color: #4a5568 #2d3748;
}
</style>