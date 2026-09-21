<script setup lang="ts">
/**
 * 「主页」那一枚房子;顶栏那一排与手机上那条底部导航都用它,同一条路径只留这一份。
 * 尺寸由调用方用 `size` 类名给(顶栏 16px、底部那条 20px);走 `currentColor`,颜色跟着用的地方走。
 */
withDefaults(defineProps<{ size?: string }>(), { size: "size-4" });
</script>

<template>
  <svg
    viewBox="0 0 24 24"
    :class="['shrink-0', size]"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M4 10.4 12 4l8 6.4V19a1 1 0 0 1-1 1h-3.5v-5h-7v5H5a1 1 0 0 1-1-1Z" />
  </svg>
</template>
