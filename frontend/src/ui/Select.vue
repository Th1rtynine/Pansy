<script setup lang="ts">
/**
 * 下拉选择,直接用浏览器自带的 `<select>`:自己画一个要处理浮层贴到屏幕边缘、点外面关掉、上下键走选项、
 * 输入法、手机上换成另一种控件、读屏软件,浏览器那个全都做了,而且免费。
 * 代价是它长得跟浏览器走,几个浏览器不完全一样(主要是那个小箭头);在「好看」与「一定能用」之间选后者。
 */
defineProps<{
  options: { value: string | number; label: string }[];
  disabled?: boolean;
}>();

const chosen = defineModel<string | number>({ default: "" });
</script>

<template>
  <select
    v-model="chosen"
    :disabled="disabled"
    class="h-8 w-full rounded-control border border-line bg-surface px-1.5 text-base text-fg disabled:bg-subtle disabled:text-disabled"
  >
    <option v-for="option in options" :key="option.value" :value="option.value">
      {{ option.label }}
    </option>
  </select>
</template>
