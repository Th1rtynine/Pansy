<script setup lang="ts">
/**
 * 标签:一个词的底,`variant`(solid / soft / outline)× `tone` × `size`(sm / md)。
 * 它只是一个词不是按钮:点上去的行为由外面套的那层决定(通常是 RouterLink),所以这里没有悬停效果,也不抢链接的样子。
 * 字重保持 400:小字号中文配可变字体插值出来的 500 会让笔画连在一起,要更清楚就加大字号,不要加字重。
 * 实心底上的字一律走 `-on` 令牌、软底走 `-soft-text`,不写 `text-white`:深色主题下底一亮一暗,写死的字就读不出来。
 */
withDefaults(
  defineProps<{
    variant?: "solid" | "soft" | "outline";
    tone?: "accent" | "neutral" | "danger" | "success" | "warning" | "info";
    size?: "sm" | "md";
  }>(),
  { variant: "soft", tone: "neutral", size: "sm" },
);

const SIZES = { sm: "h-6 px-2 text-sm", md: "h-7 px-2.5 text-base" };
const TONES: Record<string, Record<string, string>> = {
  soft: {
    // 软底兑到 48%:不能全局调淡 `--pn-accent-soft`(还有另外七处在用),只兑标签这一处。
    accent: "bg-accent-soft/48 text-accent-soft-text",
    neutral: "bg-subtle text-fg",
    danger: "bg-danger-soft text-danger-text",
    success: "bg-success-soft text-success-text",
    warning: "bg-warning-soft text-warning-text",
    info: "bg-info-soft text-info-text",
  },
  solid: {
    accent: "bg-accent text-accent-on",
    neutral: "bg-neutral-solid text-neutral-solid-on",
    danger: "bg-danger text-danger-on",
    success: "bg-success text-success-on",
    warning: "bg-warning text-warning-on",
    info: "bg-info text-info-on",
  },
  outline: {
    accent: "border border-accent text-accent-text",
    neutral: "border border-line text-muted",
    danger: "border border-danger text-danger-text",
    success: "border border-success text-success-text",
    warning: "border border-warning text-warning-text",
    info: "border border-info text-info-text",
  },
};
</script>

<template>
  <span
    :class="[
      'inline-flex items-center rounded-full whitespace-nowrap',
      SIZES[size],
      TONES[variant][tone],
    ]"
  >
    <slot />
  </span>
</template>
