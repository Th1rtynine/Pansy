<script setup lang="ts">
/**
 * 「这里什么都没有」的那一块。列表空了、搜索没结果、地址对不上时用它。
 *
 * 空状态值得写一句人话:**「暂无作品」和「没搜到」是两件事**,读者需要知道是哪一件
 * (是库里没有,还是自己找的词不对)。所以 `description` 由调用方给,不给就只显示标题。
 */
withDefaults(defineProps<{ title?: string; description?: string }>(), {});
</script>

<template>
  <div class="flex flex-col items-center gap-2 px-4 py-10 text-center">
    <span v-if="title" class="text-lg font-medium text-muted">{{ title }}</span>
    <span v-if="description" class="text-sm text-faint">{{ description }}</span>
    <span v-if="$slots.actions" class="mt-2 flex flex-wrap items-center gap-2">
      <slot name="actions" />
    </span>
  </div>
</template>
