<script setup lang="ts">
/**
 * 按钮:全站唯一的按钮。`variant`(solid / soft / outline / ghost / link)× `tone`(accent / neutral /
 * danger)× `size` 决定长什么样,页面不许自己拼颜色;悬停与按压的色不写在模板里 —— 主色实心走
 * semantic.css 的专用色阶,其余实心与链接只调透明度,聚焦外圈走 tokens.css 里那条统一规则。
 * `type` 默认 `button`:表单里的按钮忘了写 type 就会变成提交。
 */
import { computed } from "vue";
import Spinner from "./Spinner.vue";

const props = withDefaults(
  defineProps<{
    variant?: "solid" | "soft" | "outline" | "ghost" | "link";
    tone?: "accent" | "neutral" | "danger";
    size?: "sm" | "md" | "lg";
    type?: "button" | "submit" | "reset";
    loading?: boolean;
    disabled?: boolean;
    block?: boolean;
  }>(),
  { variant: "outline", tone: "neutral", size: "md", type: "button" },
);

const HEIGHTS = { sm: "h-7 px-2.5 text-sm gap-1.5", md: "h-8 px-3 text-base gap-2", lg: "h-10 px-4 text-lg gap-2" };

const TONES: Record<string, Record<string, string>> = {
  solid: {
    accent: "bg-accent text-accent-on hover:bg-accent-hover active:bg-accent-press",
    neutral: "bg-neutral-solid text-neutral-solid-on hover:opacity-(--pn-fade-hover-opacity) active:opacity-(--pn-fade-press-opacity)",
    danger: "bg-danger text-danger-on hover:opacity-(--pn-fade-hover-opacity) active:opacity-(--pn-fade-press-opacity)",
  },
  soft: {
    accent: "bg-accent-soft text-accent-text hover:bg-accent-soft/70",
    neutral: "bg-subtle text-fg hover:bg-inset",
    danger: "bg-danger-soft text-danger-text hover:bg-danger-soft/70",
  },
  outline: {
    accent: "border border-accent text-accent-text hover:bg-accent-soft",
    neutral: "border border-line text-fg hover:bg-subtle",
    danger: "border border-danger text-danger-text hover:bg-danger-soft",
  },
  ghost: {
    accent: "text-accent-text hover:bg-accent-soft",
    neutral: "text-fg hover:bg-subtle",
    danger: "text-danger-text hover:bg-danger-soft",
  },
  link: {
    accent: "text-accent-text underline underline-offset-2 hover:opacity-(--pn-fade-hover-opacity)",
    neutral: "text-fg underline underline-offset-2 hover:opacity-(--pn-fade-hover-opacity)",
    danger: "text-danger-text underline underline-offset-2 hover:opacity-(--pn-fade-hover-opacity)",
  },
};

const classes = computed(() => [
  "inline-flex items-center justify-center rounded-control font-medium transition-colors",
  "disabled:cursor-not-allowed disabled:opacity-50",
  props.variant === "link" ? "h-auto p-0" : HEIGHTS[props.size],
  TONES[props.variant][props.tone],
  props.block ? "w-full" : "",
]);
</script>

<template>
  <button :type="type" :class="classes" :disabled="disabled || loading">
    <Spinner v-if="loading" size="sm" />
    <slot />
    <slot name="trailing" />
  </button>
</template>
