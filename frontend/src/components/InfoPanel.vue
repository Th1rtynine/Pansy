<script setup lang="ts">
/**
 * 档案:一行一条的短值,给「查」用;简介是要读的正文,两者并排(左边读、右边查,窄屏右列落到下面)。
 * 标签右对齐、值左对齐、每行之间一条 1px 细线、没有斑马纹。
 * 标签列固定 `w-20`(80px,最长的标签是四个字「应有卷数」),值那一列留了 `min-w-0`,长值自己换行。
 * 列表下面那个默认插槽给计数与次级入口用(「共 15 卷」「其他载体 2」这类),它们不该占一行标签。
 */
import { Heading, Text } from "../ui";

withDefaults(defineProps<{ title?: string; rows: { label: string; value: string }[] }>(), {
  title: "档案",
});
</script>

<template>
  <section v-if="rows.length" class="flex flex-col gap-2">
    <Heading :level="2" size="sm">{{ title }}</Heading>
    <dl class="border-t border-line">
      <div v-for="row in rows" :key="row.label" class="flex gap-3 border-b border-line py-1.5">
        <dt class="w-20 shrink-0 text-right">
          <Text size="sm" tone="faint">{{ row.label }}</Text>
        </dt>
        <dd class="min-w-0 flex-1 break-all">
          <Text size="sm">{{ row.value }}</Text>
        </dd>
      </div>
    </dl>
    <slot />
  </section>
</template>
