<template v-once>
    <div class="box">
        <div class="container">
            <div class="one">
                <one />
            </div>

            <div class="DataCard">
                <DataCard />
            </div>

        </div>
    </div>
</template>
<script setup>
import one from "./one_components.vue"
import DataCard from "./DataCard.vue"
</script>
<style scoped>
.box {
    height: 100%;
    background: linear-gradient(135deg, var(--dark), var(--primary));
}
.container {
    width: 100%;
    max-width: 1800px;
    height: 100%;
    margin: 0 auto;
    padding: 0 32px;
    box-sizing: border-box;
    color: var(--text-light);
    display: flex;
    flex-direction: column;
}

.one {
    width: 100%;
    height: auto;
    margin-top: 30px;

}
.DataCard {
    width: 100%;
    height: 80%;
    margin-top: 20px;
}



/* 媒体查询 */
/* 小屏 */
@media (max-width: 991px) {
    .bigBox,.container,.one {
        margin: 0;
        padding: 0;
    }

}

</style>