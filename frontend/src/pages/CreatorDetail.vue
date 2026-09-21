<script setup lang="ts">
/**
 * 一位作者:参与过的作品按媒体类型分段。**一行是作品,不是作者** —— 角色记在作品上,同一个人在漫画里是原作、动画里可能是脚本。
 * 第一屏是**圆头像**(人像与封面要一眼分得开),「原名」那一行放**别名**。
 * 这一页自己那条筛选与顶上那条**同形不同义**(那条离开这一页去列表,这条只在本页收窄),所以带「只看」标签。
 */
import { computed, ref } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, Button, Center, Heading, SegmentedControl, Spinner, Tag, Text } from "../ui";

import { creators } from "../api";
import { labelOf, mediaTypes } from "../mediaTypes";
import { useLoad } from "../useLoad";
import CarrierRow from "../components/CarrierRow.vue";
import EntryHero from "../components/EntryHero.vue";
import InfoPanel from "../components/InfoPanel.vue";

const route = useRoute();
const chosen = ref("");

const { data, error, loading } = useLoad(
  () => creators.get(Number(route.params.id)),
  () => route.fullPath,
);

const options = computed(() => [
  { value: "", label: "全部" },
  ...mediaTypes.value.map((item) => ({ value: item.value, label: item.label })),
]);

const shown = computed(() =>
  (data.value?.credits ?? []).filter(
    (credit) => !chosen.value || credit.edition.media_type === chosen.value,
  ),
);

/** 一个类型一段,按类型那一条的顺序排。 */
const groups = computed(() => {
  const buckets = new Map<
    string,
    { edition: (typeof shown.value)[number]["edition"]; role: string }[]
  >();
  for (const credit of shown.value) {
    const members = buckets.get(credit.edition.media_type) ?? [];
    members.push({ edition: credit.edition, role: credit.role });
    buckets.set(credit.edition.media_type, members);
  }
  return mediaTypes.value
    .filter((item) => buckets.has(item.value))
    .map((item) => ({
      kind: item.value,
      label: item.label,
      members: buckets.get(item.value) ?? [],
    }));
});

const counts = computed(() => {
  const credits = data.value?.credits ?? [];
  return {
    works: new Set(credits.map((credit) => credit.edition.work_id)).size,
    editions: credits.length,
  };
});

/** 涉及哪几类,去重后按类型那一条的顺序。 */
const typeLabels = computed(() => {
  const used = new Set((data.value?.credits ?? []).map((credit) => credit.edition.media_type));
  return mediaTypes.value.filter((item) => used.has(item.value)).map((item) => item.label);
});

/** 右边那栏的档案:计数。 */
const facts = computed(() => {
  const creator = data.value;
  if (!creator) return [];
  const rows = [
    { label: "作品总标题", value: `${counts.value.works} 部` },
    { label: "作品", value: `${counts.value.editions} 份` },
  ];
  if (typeLabels.value.length) rows.push({ label: "涉及类型", value: typeLabels.value.join("、") });
  if (creator.aliases.length) rows.push({ label: "别名", value: `${creator.aliases.length} 个` });
  return rows;
});
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到这一位">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-6">
    <EntryHero shape="avatar" :lead="data.name" :title="data.name">
      <template v-if="typeLabels.length" #chips>
        <Tag v-for="label in typeLabels" :key="label" variant="soft" tone="accent" size="sm">
          {{ label }}
        </Tag>
      </template>

      <template v-if="data.aliases.length" #under>
        <Text size="sm" tone="muted">别名 {{ data.aliases.join(" · ") }}</Text>
      </template>

      <template #meta>
        <Text size="sm" tone="muted">
          参与 {{ counts.works }} 部作品总标题 · {{ counts.editions }} 份作品
        </Text>
      </template>

      <template #actions>
        <RouterLink :to="`/creators/${data.id}/edit`">
          <Button variant="outline" size="sm">编辑</Button>
        </RouterLink>
      </template>
    </EntryHero>

    <div class="flex flex-col gap-6 lg:flex-row lg:gap-8">
      <div class="flex min-w-0 flex-1 flex-col gap-5">
        <div class="flex flex-wrap items-center gap-2">
          <Text size="sm" tone="muted">只看</Text>
          <SegmentedControl v-model="chosen" :options="options" size="sm" />
        </div>

        <template v-if="groups.length">
          <section v-for="group in groups" :key="group.kind" class="flex flex-col gap-1">
            <Heading :level="2" size="lg">{{ group.label }} ({{ group.members.length }})</Heading>
            <ul class="flex flex-col divide-y divide-line">
              <CarrierRow
                v-for="member in group.members"
                :key="member.edition.id"
                :edition="member.edition"
                :note="member.role"
              />
            </ul>
          </section>
        </template>
        <Text v-else size="sm" tone="muted">
          {{ chosen ? `这位在${labelOf(chosen)}下暂无作品。` : "该作者暂无参与作品。" }}
        </Text>
      </div>

      <div class="shrink-0 lg:w-64">
        <InfoPanel :rows="facts" />
      </div>
    </div>

    <Text size="sm">
      <RouterLink class="text-accent-text" to="/works">← 回到列表</RouterLink>
    </Text>
  </div>
</template>
