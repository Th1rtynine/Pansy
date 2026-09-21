<script setup lang="ts">
/**
 * 一张载体的卡片:封面 + 分类 + 时间 + 一个计数,点整张卡进详情;作品总标题页用它而不是长条,
 * 是因为那一页只回答「有哪几份」,信息少时卡片(封面自己占面积、多列并排)才不空。
 * 名字取这一份自己的,没有名字时用类型名、那时不再重复挂类型标签;下一行是时间与计数(收录几卷)。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Cover, Tag, Text } from "../ui";

import type { EditionOut } from "../types";

const props = defineProps<{ edition: EditionOut }>();

const named = computed(() => Boolean(props.edition.title));

const countLine = computed(() => {
  const edition = props.edition;
  const parts: string[] = [];
  if (edition.published_on) parts.push(edition.published_on);
  if (edition.volumes.length) parts.push(`收录 ${edition.volumes.length}${edition.fields.unit || "卷"}`);
  else if (edition.creators.length) parts.push(`${edition.creators.length} 位作者`);
  return parts.join(" · ");
});
</script>

<template>
  <RouterLink
    :to="`/editions/${edition.id}`"
    class="flex flex-col gap-2 rounded-card border border-line p-2.5 transition-colors hover:bg-state-hover focus-visible:bg-state-hover active:bg-state-press"
  >
    <Cover
      :title="edition.title || edition.work_title"
      :src="edition.cover_url"
      :width="edition.cover_width"
      :height="edition.cover_height"
      size="card"
    />

    <span class="flex flex-col gap-1">
      <Text size="sm" weight="medium">{{ edition.title || edition.media_label }}</Text>

      <span class="flex flex-wrap items-center gap-1.5">
        <Tag v-if="named" variant="soft" tone="accent" size="sm">{{ edition.media_label }}</Tag>
        <Tag v-if="edition.release_status" variant="outline" tone="neutral" size="sm">
          {{ edition.release_status }}
        </Tag>
      </span>

      <Text v-if="countLine" size="xs" tone="faint">{{ countLine }}</Text>
    </span>
  </RouterLink>
</template>
