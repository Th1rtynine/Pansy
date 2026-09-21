<script setup lang="ts">
/**
 * 翻页:`total` 与 `itemCount`(默认 10)算出总页数,`align` 控制整条靠哪边。
 * 只有「上一页 / 下一页」加一句「第几页」,没有一排页码 —— 列表通常只有两三页,直接翻比先找自己在第几页更快。
 * `hideSinglePage` 时一页也装得下就整条不出现:「第 1 / 1 页」不提供任何信息。
 */
import { computed } from "vue";
import Button from "./Button.vue";
import Text from "./Text.vue";

const props = withDefaults(
  defineProps<{
    total: number;
    itemCount?: number;
    hideSinglePage?: boolean;
    align?: "start" | "center" | "end";
  }>(),
  { itemCount: 10, hideSinglePage: false, align: "end" },
);

const page = defineModel<number>({ default: 1 });

const pages = computed(() => Math.max(1, Math.ceil(props.total / props.itemCount)));
const hidden = computed(() => props.hideSinglePage && pages.value <= 1);
const ALIGN = { start: "justify-start", center: "justify-center", end: "justify-end" };
</script>

<template>
  <div v-if="!hidden" :class="['flex flex-wrap items-center gap-3', ALIGN[align]]">
    <Text size="sm" tone="muted">第 {{ page }} / {{ pages }} 页</Text>
    <Button size="sm" variant="outline" :disabled="page <= 1" @click="page = page - 1">
      上一页
    </Button>
    <Button size="sm" variant="outline" :disabled="page >= pages" @click="page = page + 1">
      下一页
    </Button>
  </div>
</template>
