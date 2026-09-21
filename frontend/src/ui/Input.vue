<script setup lang="ts">
/**
 * 单行输入框,`v-model` 是字符串。直接用浏览器自己的 `<input>`:手机键盘、输入法、自动填充、撤销
 * 都是现成的,没有非用不可的理由就不值得自己画一个;聚焦外圈来自 `tokens.css` 那条统一规则。
 */
withDefaults(defineProps<{ type?: string; placeholder?: string; disabled?: boolean }>(), {
  type: "text",
});

const text = defineModel<string>({ default: "" });
</script>

<template>
  <input
    v-model="text"
    :type="type"
    :placeholder="placeholder"
    :disabled="disabled"
    class="h-8 w-full rounded-control border border-line bg-surface px-2 text-base text-fg placeholder:text-disabled disabled:bg-subtle disabled:text-disabled"
  />
</template>
