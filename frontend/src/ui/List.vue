<script setup lang="ts">
/**
 * 一个列表。**行与行之间用一条细线分开,而不是每行一张卡片** —— 卡片套卡片会让一页
 * 看起来到处都是边框,而这里真正需要看清的是字。
 */
</script>

<template>
  <ul class="flex flex-col divide-y divide-line">
    <slot />
  </ul>
</template>
