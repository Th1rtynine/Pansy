<script setup lang="ts">
/**
 * 一份作品自己的页:第一屏是封面与身份(类型、状态、归属、一行元数据、编辑),下面
 * **左边读(简介、作者、标签、卷)、右边查(档案)**,最后是它连着的作品。只读。
 */
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, Button, Center, Spinner, Tag, Text } from "../ui";

import { editions } from "../api";
import { messageOf, useLoad } from "../useLoad";
import CarrierBlock from "../components/CarrierBlock.vue";
import EntryHero from "../components/EntryHero.vue";
import RelationBlock from "../components/RelationBlock.vue";

const route = useRoute();
const localNotice = ref("");
const openingLocal = ref(false);
const { data, error, loading } = useLoad(
  () => editions.get(Number(route.params.id)),
  () => route.fullPath,
);

/** 第一屏那一行:时间 · 出版方 · 数量,按这个类型的叫法(动画叫「季度」、漫画叫「卷」)。 */
const heroMeta = computed(() => {
  const edition = data.value;
  if (!edition) return "";
  const parts: string[] = [];
  if (edition.published_on) parts.push(edition.published_on);
  if (edition.org) parts.push(edition.org);
  if (edition.volume_count) parts.push(`${edition.volume_count}${edition.fields.unit ?? ""}`);
  return parts.join(" · ");
});

async function openLocal(): Promise<void> {
  if (!data.value) return;
  openingLocal.value = true;
  localNotice.value = "";
  try {
    const answer = await editions.openLocal(data.value.id);
    localNotice.value = answer.detail;
  } catch (failure) {
    localNotice.value = messageOf(failure);
  } finally {
    openingLocal.value = false;
  }
}
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到这一条">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-6">
    <EntryHero
      :lead="data.title || data.work_title"
      :title="data.title || data.work_title"
      :src="data.cover_url"
      :width="data.cover_width"
      :height="data.cover_height"
    >
      <template #chips>
        <Tag variant="soft" tone="accent" size="sm">{{ data.media_label }}</Tag>
        <Tag v-if="data.release_status" variant="outline" tone="neutral" size="sm">
          {{ data.release_status }}
        </Tag>
      </template>

      <template #under>
        <Text size="sm" tone="muted">
          属于
          <RouterLink class="text-accent-text" :to="`/works/${data.work_id}`">
            《{{ data.work_title }}》
          </RouterLink>
        </Text>
      </template>

      <template #meta>
        <Text v-if="heroMeta" size="sm" tone="muted">{{ heroMeta }}</Text>
      </template>

      <template #actions>
        <Button v-if="data.local_path" variant="solid" tone="accent" size="sm" :loading="openingLocal" @click="openLocal">
          打开资源
        </Button>
        <RouterLink :to="`/editions/${data.id}/edit`">
          <Button variant="outline" size="sm">编辑</Button>
        </RouterLink>
      </template>
    </EntryHero>

    <Alert v-if="localNotice" tone="neutral">{{ localNotice }}</Alert>

    <CarrierBlock :edition="data" />

    <RelationBlock :editions="data.relations" class="border-t border-line pt-5" />

    <Text size="sm">
      <RouterLink class="text-accent-text" :to="`/works/${data.work_id}`">
        ← 回到《{{ data.work_title }}》
      </RouterLink>
    </Text>
  </div>
</template>
