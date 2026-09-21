<script setup lang="ts">
/**
 * 一件作品总标题的页:第一屏是它自己,下面**是它有几份作品 —— 一份一张卡片**,点进卡片才看那一份的详情。
 * **界面上管一份作品就叫「作品」**,不用别的叫法 —— 读者只需要认出这是同一样东西。
 * **不在这里铺每份作品的详情** —— 简介、作者、标签、卷列表都属于「那一份是什么」,在它自己的页上看更好;信息一少长条会显空,所以用卡片。
 * 右边那栏是**这一条总标题的档案**;这一页**不收窄**,几件都铺出来。
 */
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, Button, Center, Heading, Spinner, Tag, Text } from "../ui";

import { works } from "../api";
import { useLoad } from "../useLoad";
import CarrierCard from "../components/CarrierCard.vue";
import EntryHero from "../components/EntryHero.vue";
import InfoPanel from "../components/InfoPanel.vue";
import RelationBlock from "../components/RelationBlock.vue";

const route = useRoute();
const { data, error, loading } = useLoad(
  () => works.get(Number(route.params.id)),
  () => route.fullPath,
);

const aliases = computed(() => data.value?.aliases ?? []);

/** 第一屏的类型标签:它下面出现过哪几类,去重后按出现顺序。 */
const mediaLabels = computed(() => [
  ...new Set((data.value?.editions ?? []).map((edition) => edition.media_label)),
]);

/** 右边那栏的档案。原名在标题旁边写着,这里不重复。 */
const facts = computed(() => {
  const work = data.value;
  if (!work) return [];
  const rows = [
    { label: "原作时间", value: work.published_on ?? "—" },
    { label: "作品", value: `${work.editions.length} 份` },
  ];
  if (aliases.value.length) rows.push({ label: "别名", value: `${aliases.value.length} 个` });
  if (work.linked_works.length) {
    rows.push({ label: "关联作品", value: `${work.linked_works.length} 部` });
  }
  return rows;
});
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到这一条">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-6">
    <EntryHero
      :lead="data.title"
      :title="data.title"
      :original="data.original_title"
      :src="data.cover_url ?? null"
      :width="data.cover_width ?? null"
      :height="data.cover_height ?? null"
    >
      <template v-if="mediaLabels.length" #chips>
        <Tag v-for="label in mediaLabels" :key="label" variant="soft" tone="accent" size="sm">
          {{ label }}
        </Tag>
      </template>

      <template #meta>
        <Text size="sm" tone="muted">
          原作时间 {{ data.published_on ?? "—" }} · 作品 {{ data.editions.length }} 份
        </Text>
      </template>

      <template #actions>
        <RouterLink :to="`/works/${data.id}/edit`">
          <Button variant="outline" size="sm">编辑</Button>
        </RouterLink>
      </template>
    </EntryHero>

    <div class="flex flex-col gap-6 lg:flex-row lg:gap-8">
      <div class="flex min-w-0 flex-1 flex-col gap-5">
        <Heading :level="2" size="lg">作品 ({{ data.editions.length }})</Heading>

        <div v-if="data.editions.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-4">
          <CarrierCard v-for="edition in data.editions" :key="edition.id" :edition="edition" />
        </div>
        <Text v-else size="sm" tone="muted">该作品总标题下暂无作品。</Text>

        <RelationBlock :works="data.linked_works" class="border-t border-line pt-5" />
      </div>

      <div class="shrink-0 lg:w-64">
        <InfoPanel :rows="facts">
          <Text size="sm" tone="faint">
            别名 {{ aliases.length ? aliases.join(" · ") : "—" }}
          </Text>
        </InfoPanel>
      </div>
    </div>

    <Text size="sm">
      <RouterLink class="text-accent-text" to="/works">← 回到列表</RouterLink>
    </Text>
  </div>
</template>
