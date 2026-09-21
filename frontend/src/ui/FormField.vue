<script setup lang="ts">
/**
 * 表单里的一格:`label` + `description` + 控件本身,`required` 只在标题旁加一个「必填」。
 * 说明文字必须贴着输入框,不能放页脚 —— 人在敲字的时候才会读它。
 * 它不校验:校验只有后端一份,错误由页面用 Alert 显示。
 */
withDefaults(defineProps<{ label?: string; description?: string; required?: boolean }>(), {});
</script>

<template>
  <label class="flex flex-col gap-1">
    <span v-if="label" class="text-sm font-medium text-fg">
      {{ label }}
      <span v-if="required" class="text-xs font-normal text-faint">必填</span>
    </span>
    <slot />
    <span v-if="description" class="text-xs text-faint">{{ description }}</span>
  </label>
</template>
