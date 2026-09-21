<script setup lang="ts">
/**
 * 右下角那枚「回到上一页」,固定在「回到顶部」上面一格、与它对齐(`bottom-[10.5rem]`)。
 * 回的是**上一个页面**,不是层级父页:规则与边界见 `src/trail.ts`,这里只管画与点。
 * 形状、位置、颜色照抄 `BackToTop.vue`(含右边距里的 `100%` 与 `var(--pn-shell-width)`,理由在那边)。
 * 它不随滚动出现 —— 上一页是刚到一页时就想按的东西。
 */
import { useRoute, useRouter } from "vue-router";

import { takePrevious } from "../trail";

const route = useRoute();
const router = useRouter();

function goBack() {
  router.push(takePrevious(route.fullPath));
}
</script>

<template>
  <button
    type="button"
    aria-label="回到上一页"
    title="回到上一页"
    :class="[
      'fixed bottom-[10.5rem] z-(--pn-z-overlay) flex size-10 items-center justify-center',
      'right-[max(1rem,calc((100%-var(--pn-shell-width))/2-5rem))]',
      'rounded-control border border-line bg-surface/80 text-muted backdrop-blur-sm',
      'transition-colors hover:bg-surface hover:text-fg active:bg-state-press',
    ]"
    @click="goBack"
  >
    <!-- 圆头的向左箭头:与「回到顶部」同一套画法(圆头、无尖角、同样的线宽) -->
    <svg
      viewBox="0 0 24 24"
      class="size-5"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M18.5 12H6" />
      <path d="M11.5 6.5 6 12l5.5 5.5" />
    </svg>
  </button>
</template>
