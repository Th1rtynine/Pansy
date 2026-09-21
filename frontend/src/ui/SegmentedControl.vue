<script setup lang="ts">
/**
 * 一条里面选一个:`options` 是 `{ value, label }[]`,`size` 分 sm / md。
 * 不做成下拉是因为一共就四五个选项:全摆出来一眼看完,点一下就换,下拉要多两次操作(点开、选)还看不到有哪些可选。
 * 它渲染成按钮不是链接,换选项后改地址由页面负责。
 */
withDefaults(
  defineProps<{
    options: { value: string | number; label: string }[];
    size?: "sm" | "md";
    disabled?: boolean;
  }>(),
  { size: "md" },
);

const chosen = defineModel<string | number>({ default: "" });

const HEIGHTS = { sm: "h-7 px-2.5 text-sm", md: "h-8 px-3 text-base" };
</script>

<template>
  <div
    class="inline-flex flex-wrap items-center gap-0.5 rounded-control bg-subtle p-0.5"
    role="group"
  >
    <button
      v-for="option in options"
      :key="option.value"
      type="button"
      :disabled="disabled"
      :aria-pressed="option.value === chosen"
      :class="[
        'rounded-[5px] font-medium transition-colors disabled:opacity-50',
        HEIGHTS[size],
        option.value === chosen
          ? 'bg-surface text-fg shadow-sm'
          : 'text-muted hover:text-fg',
      ]"
      @click="chosen = option.value"
    >
      {{ option.label }}
    </button>
  </div>
</template>
