<script setup lang="ts">
/**
 * 列表页的页头:一个标题、一句计数(或说明)、右上角的动作、标题下面那一行工具。
 * 三个列表页(作品、作者、标签)共用这一层,所以计数统一在标题下面 —— 它是「你现在看到多少」,
 * 属于页头不属于页脚,页脚只留翻页。标题用 `xl`(与表单页一致):列表页的标题是导航,不是内容。
 */
import { Heading, Text } from "../ui";

withDefaults(defineProps<{ title: string; note?: string }>(), { note: "" });
</script>

<template>
  <div class="flex flex-col gap-4 border-b border-line pb-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div class="flex min-w-0 flex-col gap-1">
        <Heading :level="1" size="xl">{{ title }}</Heading>
        <Text v-if="note" size="sm" tone="muted">{{ note }}</Text>
      </div>

      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="$slots.tools" class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <slot name="tools" />
    </div>
  </div>
</template>
