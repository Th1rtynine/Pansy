<script setup lang="ts">
/**
 * 数字输入框,用浏览器自带的 `<input type="number">`:上下键、步进、手机数字键盘都是现成的。
 * `v-model` 只有两种值:数字或「空」(null)—— 空表示「我没填」而不是 0,卷号可以留空,留空与填 0 是两件事。
 * 输入字母时浏览器自己会报「不是数字」,值是空的;真正的校验只有后端一份。
 */
const props = withDefaults(
  defineProps<{ min?: number; max?: number; step?: number; placeholder?: string; disabled?: boolean }>(),
  { step: 1 },
);

const value = defineModel<number | null>({ default: null });

function onInput(event: Event) {
  const raw = (event.target as HTMLInputElement).value;
  value.value = raw === "" ? null : Number(raw);
}
</script>

<template>
  <input
    type="number"
    :value="value === null ? '' : value"
    :min="props.min"
    :max="props.max"
    :step="props.step"
    :placeholder="placeholder"
    :disabled="disabled"
    class="h-8 w-full rounded-control border border-line bg-surface px-2 text-base text-fg placeholder:text-disabled disabled:bg-subtle"
    @input="onInput"
  />
</template>
