<script setup lang="ts">
/**
 * 一组词:别名、标签这类「可以有零个或多个」的字段,`v-model` 是 `string[]`,另有一个 `typed` 是正在敲的那半截。
 * 回车加一个、点叉去掉一个、空着按退格去掉最后一个;做成一格一格的片子而不是逗号分隔,是因为逗号也是词里可能出现的字符。
 * 它不抢输入:外面套一个 `<label>`(Field 就是),点片子之间的空白也落在输入框上。
 */
import CloseButton from "./CloseButton.vue";

withDefaults(defineProps<{ placeholder?: string }>(), { placeholder: "输入后回车" });

const items = defineModel<string[]>({ default: () => [] });
const typed = defineModel<string>("typed", { default: "" });

function add() {
  const value = typed.value.trim();
  if (!value) return;
  if (!items.value.includes(value)) items.value = [...items.value, value];
  typed.value = "";
}

function drop(index: number) {
  items.value = items.value.filter((_, position) => position !== index);
}

function onBackspace() {
  if (typed.value === "" && items.value.length) items.value = items.value.slice(0, -1);
}
</script>

<template>
  <div
    class="flex min-h-8 flex-wrap items-center gap-1.5 rounded-control border border-line bg-surface px-1.5 py-1"
  >
    <span
      v-for="(item, index) in items"
      :key="item"
      class="inline-flex items-center gap-1 rounded-full bg-subtle px-2 py-0.5 text-sm text-fg"
    >
      {{ item }}
      <CloseButton :label="`去掉 ${item}`" @click="drop(index)" />
    </span>
    <input
      v-model="typed"
      :placeholder="items.length ? '' : placeholder"
      class="h-6 min-w-32 flex-1 bg-transparent text-base text-fg outline-none placeholder:text-disabled"
      @keydown.enter.prevent="add"
      @keydown.backspace="onBackspace"
      @blur="add"
    />
  </div>
</template>
