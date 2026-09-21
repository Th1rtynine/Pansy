<script setup lang="ts">
/**
 * 一个小小的叉。用在一格一格的词上、搜索框上。
 *
 * 它是按钮(能 Tab 到、能回车),但比正常的按钮小得多,所以单独一个组件 —— 免得两个
 * 地方各画一次,其中一处忘了 `type="button"` 或忘了给读屏软件留个名字。
 */
withDefaults(defineProps<{ label: string }>(), {});
</script>

<template>
  <button
    type="button"
    :aria-label="label"
    :title="label"
    class="inline-flex size-4 items-center justify-center rounded-full text-faint hover:bg-inset hover:text-fg"
  >
    <svg viewBox="0 0 12 12" class="size-2.5" aria-hidden="true">
      <path d="M1 1 L11 11 M11 1 L1 11" stroke="currentColor" stroke-width="1.6" fill="none" />
    </svg>
  </button>
</template>
