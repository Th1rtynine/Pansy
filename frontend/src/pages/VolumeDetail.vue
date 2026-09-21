<script setup lang="ts">
/**
 * 一卷自己的页,**与作品页同一套骨架** —— 不做成「小的第一屏」,否则三层级里最深那一级忽然换个样子。
 * **要取两次**:卷这一层只带 `edition_id`,而「所属作品」那一行要写出名字,所以拿到卷之后再取它所属的那一份作品。
 */
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, Button, Center, Spinner, Text } from "../ui";

import { editions, volumes } from "../api";
import { useLoad } from "../useLoad";
import EntryHero from "../components/EntryHero.vue";
import InfoPanel from "../components/InfoPanel.vue";

const route = useRoute();

const { data, error, loading } = useLoad(
  async () => {
    const volume = await volumes.get(Number(route.params.id));
    const edition = await editions.get(volume.edition_id);
    return { volume, edition };
  },
  () => route.fullPath,
);

/** 这一卷量词用哪一个:问它所属那一份作品的类型表,游戏就是「话」,漫画就是「卷」。 */
const unit = computed(() => data.value?.edition.fields.unit || "卷");

const label = computed(() => {
  const volume = data.value?.volume;
  if (!volume) return "";
  if (volume.volume_number === null) return volume.title || unit.value;
  return `第 ${volume.volume_number} ${unit.value}`;
});

const panelRows = computed(() => {
  const loaded = data.value;
  if (!loaded) return [];
  return [
    { label: "序号", value: loaded.volume.volume_number === null ? "—" : label.value },
    { label: "所属作品", value: `《${loaded.edition.work_title}》 · ${loaded.edition.media_label}` },
  ];
});
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到这一条">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-5">
    <EntryHero
      :lead="data.volume.title || label"
      :title="data.volume.title || label"
      :src="data.volume.cover_url"
      :width="data.volume.cover_width"
      :height="data.volume.cover_height"
    >
      <template #under>
        <!-- 有名字时序号才有信息量;没有名字时标题那一行本身就是「第 4 卷」 -->
        <Text v-if="data.volume.title" size="base" tone="faint">{{ label }}</Text>
      </template>

      <template #meta>
        <Text size="sm" tone="muted">
          所属作品
          <RouterLink class="text-accent-text" :to="`/editions/${data.edition.id}`">
            《{{ data.edition.work_title }}》 · {{ data.edition.media_label }}
          </RouterLink>
        </Text>
      </template>

      <template #actions>
        <RouterLink :to="`/volumes/${data.volume.id}/edit`">
          <Button variant="outline" size="sm">编辑</Button>
        </RouterLink>
      </template>
    </EntryHero>

    <div class="flex flex-col gap-5 lg:flex-row lg:gap-8">
      <div class="flex min-w-0 flex-1 flex-col gap-3">
        <Text as="p">{{ data.volume.summary || "—" }}</Text>
      </div>

      <div class="shrink-0 lg:w-64">
        <InfoPanel :rows="panelRows">
          <RouterLink class="text-sm text-accent-text" :to="`/editions/${data.edition.id}`">
            回到《{{ data.edition.work_title }}》 →
          </RouterLink>
        </InfoPanel>
      </div>
    </div>
  </div>
</template>
