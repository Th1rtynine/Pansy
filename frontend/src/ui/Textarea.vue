<script setup lang="ts">
/** 多行输入框。简介、别名这类「一段话」的字段用它。 */
withDefaults(defineProps<{ rows?: number; placeholder?: string }>(), { rows: 4 });

const text = defineModel<string>({ default: "" });
</script>

<template>
  <textarea
    v-model="text"
    :rows="rows"
    :placeholder="placeholder"
    class="w-full resize-y rounded-control border border-line bg-surface px-2 py-1.5 text-base text-fg placeholder:text-disabled"
  />
</template>
