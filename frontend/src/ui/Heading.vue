<script setup lang="ts">
/**
 * 标题。`level` 决定它是 `<h1>` 还是 `<h3>`(这影响读屏软件与大纲),`size` 决定它看起来
 * 多大 —— **两者分开是有意的**:一页里标题的层级与技术上的标签不该被字号绑死。
 *
 * `break-words` 与 `Text.vue` 同一个理由:中文按字断行不怕长,没有空格的长串会顶破框。
 */
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    level?: 1 | 2 | 3 | 4 | 5 | 6;
    size?: "sm" | "base" | "lg" | "xl" | "2xl";
  }>(),
  { level: 2, size: "lg" },
);

const SIZES = {
  sm: "text-sm",
  base: "text-base",
  lg: "text-lg",
  xl: "text-xl",
  "2xl": "text-2xl",
};

const classes = computed(() => [
  SIZES[props.size],
  props.level <= 2 ? "font-semibold text-fg" : "font-medium text-fg",
  "flex flex-wrap items-baseline gap-x-2 break-words",
]);
</script>

<template>
  <component :is="`h${props.level}`" :class="classes">
    <slot />
  </component>
</template>
