<script setup lang="ts">
/**
 * 一条提示:出错、成功、说明。语气决定颜色,颜色一律从令牌来。
 *
 * **它是消息,不是弹窗**:没有要处理的东西时,消息应该待在页面里、不动、也不需要人去
 * 关掉它 —— 会自己消失的浮层在「我刚才到底存成没成」这件事上帮倒忙。
 */
withDefaults(
  defineProps<{
    tone?: "accent" | "neutral" | "danger" | "success" | "warning" | "info";
    title?: string;
  }>(),
  { tone: "neutral" },
);

const TONES: Record<string, string> = {
  accent: "bg-accent-soft text-accent-text",
  neutral: "bg-subtle text-muted",
  danger: "bg-danger-soft text-danger-text",
  success: "bg-success-soft text-success-text",
  warning: "bg-warning-soft text-warning-text",
  info: "bg-info-soft text-info-text",
};
</script>

<template>
  <div :class="['rounded-card px-3 py-2 text-base', TONES[tone]]" role="alert">
    <span v-if="title" class="font-medium">{{ title }}</span>
    <span :class="title ? 'ml-2' : ''"><slot /></span>
  </div>
</template>
