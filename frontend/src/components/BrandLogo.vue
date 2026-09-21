<script setup lang="ts">
import pansyMark from "../assets/pansy-mark-v3.png";
</script>

<template>
  <!--
    站名由文字与一枚极简五瓣三色堇组成。花图使用专门为 20–32px 尺寸生成并压缩的透明 PNG;
    这个组件只负责外观,回首页的链接与无障碍名称由 App.vue 提供。
  -->
  <span class="inline-flex h-9 items-center gap-1.5 whitespace-nowrap" aria-hidden="true">
    <span class="brand-word">Pansy</span>
    <img
      :src="pansyMark"
      alt=""
      width="28"
      height="28"
      decoding="async"
      class="h-7 w-7 shrink-0 object-contain"
    />
  </span>
</template>

<style scoped>
.brand-word {
  font-family: var(--font-brand);
  font-size: 2.2rem;
  font-style: italic;
  font-weight: 500;
  line-height: 0.8;
  letter-spacing: 0.01em;
}
</style>
