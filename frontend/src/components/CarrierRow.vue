<script setup lang="ts">
/**
 * 列表里的一行:一份作品,作者页、标签页与选了类型后的列表共用,所以它们不会各自漂移。
 * 上一层(作品总标题)是另一种东西,有自己的一段(WorkRow.vue);左边同样有封面位。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Cover, Tag, Text } from "../ui";

import type { EditionRef } from "../types";

const props = defineProps<{
  edition: EditionRef;
  /** 次要的那一行:角色、命中在哪一项之类;没有就不显示。 */
  note?: string;
  /** 这一行点到哪里;不传就是这份作品自己的页。 */
  to?: string;
}>();

/** 作品有自己的标题时,作品总标题作为归属跟在后面;没有就不重复写两遍名字。 */
const meta = computed(() => {
  const parts: string[] = [];
  if (props.edition.published_on) parts.push(props.edition.published_on);
  if (props.edition.title) parts.push(props.edition.work_title);
  if (props.note) parts.push(props.note);
  return parts.join(" · ");
});
</script>

<template>
  <li>
    <RouterLink
      :to="to ?? `/editions/${edition.id}`"
      class="flex items-start gap-3 rounded-control px-3 py-3 transition-colors hover:bg-state-hover focus-visible:bg-state-hover active:bg-state-press"
    >
      <Cover
        :title="edition.title || edition.work_title"
        :src="edition.cover_url"
        :width="edition.cover_width"
        :height="edition.cover_height"
      />

      <!-- min-w-0 不能省,理由同 WorkRow.vue -->
      <span class="flex min-w-0 flex-1 flex-col gap-1">
        <span class="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <Text size="lg" weight="semibold">{{ edition.title || edition.work_title }}</Text>
          <Tag variant="soft" tone="neutral" size="sm">{{ edition.media_label }}</Tag>
        </span>
        <Text v-if="meta" size="sm" tone="muted">{{ meta }}</Text>
      </span>
    </RouterLink>
  </li>
</template>
