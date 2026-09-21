<script setup lang="ts">
/**
 * 列表里的一行:一件作品总标题,左边是封面位(见 ui/Cover.vue)。
 * 一行说什么:名字在上,原名跟在后面;下面一行次要信息,依次是原作时间、这次搜索命中在哪一项、
 * 它有哪几件作品。时间在最前是有意的 —— 列表可以按它排,读者要能一眼看出顺序是怎么来的。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Cover, Tag, Text } from "../ui";

import type { WorkOut } from "../types";

const props = defineProps<{ work: WorkOut }>();

const note = computed(() => {
  const parts: string[] = [];
  if (props.work.matched_by.length) parts.push(`命中 ${props.work.matched_by.join("、")}`);
  const labels = props.work.editions.map((edition) => edition.media_label);
  parts.push(labels.length ? labels.join(" · ") : "尚未建立作品");
  return parts.join(" · ");
});
</script>

<template>
  <li>
    <RouterLink
      :to="`/works/${work.id}`"
      class="flex items-start gap-3 rounded-control px-3 py-3 transition-colors hover:bg-state-hover focus-visible:bg-state-hover active:bg-state-press"
    >
      <Cover
        :title="work.title"
        :src="work.cover_url ?? null"
        :width="work.cover_width ?? null"
        :height="work.cover_height ?? null"
      />

      <!-- min-w-0 不能省:没有它,长标题会把这一列撑开,把封面挤扁,而不是自己换行 -->
      <span class="flex min-w-0 flex-1 flex-col gap-1">
        <span class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Text size="lg" weight="semibold">{{ work.title }}</Text>
          <Text v-if="work.original_title" size="sm" tone="muted">
            {{ work.original_title }}
          </Text>
        </span>
        <span class="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Tag v-if="work.published_on" variant="outline" tone="neutral" size="sm">
            {{ work.published_on }}
          </Tag>
          <Text size="sm" tone="muted">{{ note }}</Text>
        </span>
      </span>
    </RouterLink>
  </li>
</template>
