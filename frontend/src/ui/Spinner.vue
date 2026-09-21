<script setup lang="ts">
/**
 * 转圈,用在「正在读」的地方:`size` 分 sm / md / lg,`label` 给读屏软件(默认「正在读取」)。
 * 它是一圈边框转起来,不是图片也不是字体图标 —— 少一个请求,颜色还跟着主色走。
 * 知道大概要等多久、内容大概多长的地方要用灰条占位(骨架屏),不是这个。
 */
withDefaults(defineProps<{ size?: "sm" | "md" | "lg"; label?: string }>(), { size: "md" });

const SIZES = { sm: "size-3.5 border-[1.5px]", md: "size-5 border-2", lg: "size-7 border-2" };
</script>

<template>
  <span
    :class="['inline-block animate-spin rounded-full border-current border-r-transparent align-[-0.125em]', SIZES[size]]"
    role="status"
    :aria-label="label ?? '正在读取'"
  />
</template>
