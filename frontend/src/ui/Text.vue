<script setup lang="ts">
/**
 * 一段文字,全站的正文与次要信息都走它。`as` 默认渲染成 `<span>` 而不是 `<p>`:它经常被放在标题里、
 * 链接里、按钮旁边,那里块级套行内是错的;真要独占一行就在外面套一个 `<p>`,或者传 `as="p"`。
 * `tone` 只有三级(正文 / 次要 / 再次要),对应令牌里的三级灰 —— 层级靠浓度分不靠字号,一行里混排才不会一跳一跳。
 * `break-words` 不能省:没有空格的长串(罗马字原名、粘来的链接、长文件名)会顶破所在的框,窄屏上撑出横向滚动条。
 */
withDefaults(
  defineProps<{
    as?: string;
    size?: "xs" | "sm" | "base" | "lg" | "xl" | "2xl";
    tone?: "default" | "muted" | "faint" | "accent" | "danger" | "success";
    weight?: "normal" | "medium" | "semibold";
  }>(),
  { as: "span", size: "base", tone: "default", weight: "normal" },
);

const SIZES = {
  xs: "text-xs",
  sm: "text-sm",
  base: "text-base",
  lg: "text-lg",
  xl: "text-xl",
  "2xl": "text-2xl",
};
const TONES = {
  default: "text-fg",
  muted: "text-muted",
  faint: "text-faint",
  accent: "text-accent-text",
  danger: "text-danger-text",
  success: "text-success-text",
};
const WEIGHTS = { normal: "font-normal", medium: "font-medium", semibold: "font-semibold" };
</script>

<template>
  <component :is="as" :class="['break-words', SIZES[size], TONES[tone], WEIGHTS[weight]]">
    <slot />
  </component>
</template>
