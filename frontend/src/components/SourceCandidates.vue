<script setup lang="ts">
/**
 * 「用那个名字找到的这些,挑要加入的」那一块。**它不含输入框** —— 搜索入口在作品名那一格上(见 `pages/AddWork.vue`),
 * 这里只画候选、收勾选,再把勾中的每组报回页面。**按类型分段,同名的几条并排**:后端已认出「同一条记录」,
 * 并排的就是它在两个站上的样子,都勾上就都记住;**一个源在一组里最多勾一条**,分组只是建议,只有人自己敲的
 * ID(`resolved`)默认勾着。**一组一张卡片、卡片里各源各一行**,来源增加时自然向下延伸。
 */
import { computed, ref, watch } from "vue";
import { Button, Heading, Text } from "../ui";

import { sources } from "../api";
import { labelOf, mediaTypes } from "../mediaTypes";
import { labelOfSource } from "../sourceNames";
import type { PickedCarrier, SourceCandidate } from "../types";

const props = withDefaults(
  defineProps<{
    candidates: SourceCandidate[];
    /** 人点名要的那一条(敲的是条目 ID 时才有):它默认勾着。 */
    resolved?: SourceCandidate | null;
    /** 只决定同一具体版本里谁优先提供字段，不改变版本归组。 */
    sourcePriority?: string[];
  }>(),
  { resolved: null, sourcePriority: () => [] },
);

const emit = defineEmits<{ picks: [PickedCarrier[]] }>();

const showAll = ref(false);
/** 空数组就是「全部」；选中一个或多个类型后，只保留那些类型。 */
const selectedMedia = ref<string[]>([]);
/** 旧后端没有 `match_score` 时照常显示;新后端的 0 分项默认收在「其余结果」里。 */
const matchedCandidates = computed(() =>
  props.candidates.filter((item) => (item.match_score ?? 1) > 0),
);
const hiddenCount = computed(() => props.candidates.length - matchedCandidates.value.length);
const visibleCandidates = computed(() =>
  showAll.value ? props.candidates : matchedCandidates.value,
);
const approximate = computed(
  () => matchedCandidates.value.length > 0 && matchedCandidates.value.every((item) => item.match_approximate),
);

/** 一组候选:同一个具体版本在几个站上的样子。 */
type Row = { key: string; media: string; name: string; items: SourceCandidate[] };

/** 勾中的:`组|源` → 那一条。一个源在一个组里最多一条。 */
const chosen = ref<Record<string, SourceCandidate>>({});
/** 勾中的那几条里**已经在库里的**是哪些。早问一句能省一整屏的力气:不加这一步,人要把整屏填完、点保存,才被那条唯一索引挡回来说「已经记在另一件作品上了」。 */
const claimed = ref<Record<string, { work_title: string; edition_id: number }>>({});

/**
 * 后端回的候选 → 先按「类型 + 归一化名字」找同名项，再保守地判断哪些可以跨来源放在一起。
 *
 * 标题只负责召回，不能单独决定身份：同一原作可能有两部完全同名的漫画。之前这里按来源返回顺序把
 * “每个来源的第一条”塞进一组，结果会把 Bangumi 的 2016 版和 Hikarinagi 的 2019 版配在一起。
 * 现在的规则是：
 *
 * - 同名项在每个来源都只有一条时，可以作为一组建议；
 * - 某个来源出现多条同名版本时，只合并「年份相同且每个来源在该年份都只有一条」的候选；
 * - 证据仍不够的候选各自成组，宁可让人稍后确认，也不把两个版本的作者、卷册与日期串起来。
 *
 * 这只是选择页的保守归组，不会替用户勾选，也不会把年份当成永久身份。保存后的身份仍由外部 ID 记录。
 */
const rows = computed<Row[]>(() => {
  type Indexed = { item: SourceCandidate; index: number };
  type Cluster = { key: string; first: number; items: Indexed[] };

  const buckets = new Map<string, Indexed[]>();
  visibleCandidates.value.forEach((item, index) => {
    const key = `${item.media ?? ""}|${item.group}`;
    buckets.set(key, [...(buckets.get(key) ?? []), { item, index }]);
  });

  const clusters: Cluster[] = [];
  for (const [baseKey, bucket] of buckets) {
    const sourceCounts = new Map<string, number>();
    for (const { item } of bucket) {
      sourceCounts.set(item.source, (sourceCounts.get(item.source) ?? 0) + 1);
    }

    // 没有同一来源的同名多版本时，标题足以把几个来源摆在同一张建议卡里。
    if ([...sourceCounts.values()].every((count) => count === 1)) {
      clusters.push({ key: baseKey, first: bucket[0].index, items: bucket });
      continue;
    }

    const used = new Set<number>();
    const byYear = new Map<string, Indexed[]>();
    for (const entry of bucket) {
      const year = entry.item.year?.trim();
      if (year) byYear.set(year, [...(byYear.get(year) ?? []), entry]);
    }

    // 年份只在同一个来源没有歧义、并且至少两个来源相互印证时才作为配对证据。
    for (const [year, entries] of byYear) {
      const perSource = new Map<string, number>();
      for (const { item } of entries) {
        perSource.set(item.source, (perSource.get(item.source) ?? 0) + 1);
      }
      if (perSource.size < 2 || [...perSource.values()].some((count) => count !== 1)) continue;
      clusters.push({
        key: `${baseKey}|year:${year}`,
        first: Math.min(...entries.map((entry) => entry.index)),
        items: entries,
      });
      entries.forEach((entry) => used.add(entry.index));
    }

    // 缺年份、年份不一致或同年仍有多条时不猜，每条单独保留。
    for (const entry of bucket) {
      if (used.has(entry.index)) continue;
      clusters.push({
        key: `${baseKey}|entry:${entry.item.source}:${entry.item.external_id}`,
        first: entry.index,
        items: [entry],
      });
    }
  }

  return clusters
    .sort((left, right) => left.first - right.first)
    .map((cluster) => {
      const priority = (source: string) => {
        const rank = props.sourcePriority.indexOf(source);
        return rank < 0 ? props.sourcePriority.length : rank;
      };
      const items = cluster.items
        .sort((left, right) => priority(left.item.source) - priority(right.item.source) || left.index - right.index)
        .map(({ item }) => item);
      const head = items[0];
      return {
        key: cluster.key,
        media: head.media ?? "",
        name: head.title || head.original_title || head.external_id,
        items,
      };
    });
});

/** 再按类型分段:类型的顺序与全站一致(漫画、轻小说、Gal、动画),猜不出类型的排最后。 */
const allSections = computed(() => {
  const rank = new Map(mediaTypes.value.map((item, index) => [item.value, index]));
  const seen = new Map<string, { media: string; label: string; rows: Row[] }>();
  for (const row of rows.value) {
    if (!seen.has(row.media)) {
      seen.set(row.media, {
        media: row.media,
        label: row.media ? labelOf(row.media) : "类型不明",
        rows: [],
      });
    }
    seen.get(row.media)!.rows.push(row);
  }
  return [...seen.values()].sort(
    (left, right) =>
      (rank.get(left.media) ?? mediaTypes.value.length) -
      (rank.get(right.media) ?? mediaTypes.value.length),
  );
});

const sections = computed(() =>
  selectedMedia.value.length
    ? allSections.value.filter((section) => selectedMedia.value.includes(section.media))
    : allSections.value,
);

/** 哪些组被勾了东西 —— 一组一件作品,所以勾了才有一份要填的表单。
 *  **顺序照页面上看到的来**(按类型分段那一份):两套顺序会让人把「第 2 件」对到错的那一组上。 */
const picked = computed(() =>
  sections.value.flatMap((section) =>
    section.rows
      .map((row) => ({ row, items: row.items.filter((item) => isChosen(row, item)) }))
      .filter((entry) => entry.items.length > 0),
  ),
);

// 换了一批候选(又搜了一次),上一次勾的就不作数了;人点名的那一条重新默认勾上。
// **`immediate` 不能省**:这一块只在搜过之后才出现,所以「第一次搜」对它来说是挂载,不是「候选变了」。
watch(
  () => props.candidates,
  () => {
    showAll.value = false;
    selectedMedia.value = [];
    chosen.value = {};
    claimed.value = {};
    const resolved = props.resolved;
    if (resolved) {
      const row = rows.value.find((row) =>
        row.items.some(
          (item) => item.source === resolved.source && item.external_id === resolved.external_id,
        ),
      );
      if (row) {
        chosen.value = Object.fromEntries(row.items.map((item) => [slotOf(row, item), item]));
        void Promise.all(row.items.map(askClaim));
      }
    }
    announce();
  },
  { immediate: true },
);

function slotOf(row: Row, item: SourceCandidate): string {
  return `${row.key}|${item.source}`;
}

function isChosen(row: Row, item: SourceCandidate): boolean {
  return chosen.value[slotOf(row, item)]?.external_id === item.external_id;
}

function claimOf(item: SourceCandidate) {
  return claimed.value[`${item.source}|${item.external_id}`];
}

/** 这一格的头:有封面的那一条(封面、原名都从它来),一条都没有就用第一条。 */
function headOf(row: Row): SourceCandidate | undefined {
  return row.items.find((item) => item.cover_url) ?? row.items[0];
}

/** 这一格里勾了什么没有 —— 勾了的那一格整张卡片换色。 */
function anyChosen(row: Row): boolean {
  return row.items.some((item) => isChosen(row, item));
}

function announce(): void {
  emit(
    "picks",
    picked.value.map(({ row, items }) => ({
      key: row.key,
      media: row.media,
      name: row.name,
      items,
    })),
  );
}

function toggleMedia(media: string): void {
  const current = selectedMedia.value;
  selectedMedia.value = current.includes(media)
    ? current.filter((value) => value !== media)
    : [...current, media];

  // 选了形式就表示只加入这些形式；被筛掉的勾选不能躲在页面外继续生成表单。
  if (selectedMedia.value.length) {
    const allowed = new Set(selectedMedia.value);
    chosen.value = Object.fromEntries(
      Object.entries(chosen.value).filter(([, item]) => allowed.has(item.media ?? "")),
    );
  }
  announce();
}

function showEveryMedia(): void {
  selectedMedia.value = [];
  announce();
}

function toggleOtherResults(): void {
  if (showAll.value) {
    const next = Object.fromEntries(
      Object.entries(chosen.value).filter(([, item]) => (item.match_score ?? 1) > 0),
    );
    chosen.value = next;
    showAll.value = false;
    const available = new Set(rows.value.map((row) => row.media));
    selectedMedia.value = selectedMedia.value.filter((media) => available.has(media));
    announce();
    return;
  }
  showAll.value = true;
}

async function toggle(row: Row): Promise<void> {
  const next = { ...chosen.value };
  if (!anyChosen(row)) {
    for (const member of row.items) next[slotOf(row, member)] = member;
  } else {
    for (const member of row.items) delete next[slotOf(row, member)];
  }
  chosen.value = next;
  announce();
  await Promise.all(row.items.filter((member) => next[slotOf(row, member)]).map(askClaim));
}

async function askClaim(item: SourceCandidate): Promise<void> {
  const key = `${item.source}|${item.external_id}`;
  if (claimed.value[key]) return;
  try {
    const owner = await sources.claims(item.source, item.external_id);
    if (owner) {
      claimed.value = {
        ...claimed.value,
        [key]: { work_title: owner.work_title, edition_id: owner.edition_id },
      };
    }
  } catch {
    // 问不到就当没人认领:这一句只是提前提醒,拦人的那道墙在保存那一步。
  }
}
</script>

<template>
  <div class="flex flex-col gap-3">
    <Text v-if="approximate" size="sm" tone="muted">
      没有完全一致的标题，以下按拼写相近程度排列。
    </Text>

    <div v-if="allSections.length > 1" class="flex flex-wrap items-center gap-1.5">
      <Text size="sm" tone="muted" class="mr-1">作品形式</Text>
      <Button
        size="sm"
        :variant="selectedMedia.length ? 'ghost' : 'soft'"
        :tone="selectedMedia.length ? 'neutral' : 'accent'"
        :aria-pressed="!selectedMedia.length"
        @click="showEveryMedia"
      >
        全部 {{ rows.length }}
      </Button>
      <Button
        v-for="section in allSections"
        :key="section.media"
        size="sm"
        :variant="selectedMedia.includes(section.media) ? 'soft' : 'ghost'"
        :tone="selectedMedia.includes(section.media) ? 'accent' : 'neutral'"
        :aria-pressed="selectedMedia.includes(section.media)"
        @click="toggleMedia(section.media)"
      >
        {{ section.label }} {{ section.rows.length }}
      </Button>
      <Text v-if="selectedMedia.length" size="xs" tone="faint">可多选</Text>
    </div>

    <!-- 结果放进一块有边界的浏览区。来源继续增加时页面不会被候选无限拉长。 -->
    <div
      v-if="rows.length"
      class="isolate max-h-[36rem] overflow-y-auto overscroll-contain rounded-card border border-line bg-subtle"
    >
      <div class="flex flex-col gap-3 pb-2">
        <!-- 按类型分段:分野只是建议,勾哪一条由人定。 -->
        <div v-for="section in sections" :key="section.media" class="flex min-w-0 flex-col gap-1.5">
          <div class="sticky top-0 z-10 flex items-center gap-2 border-b border-line bg-subtle px-2 py-1.5 sm:px-3">
            <Heading :level="3" size="base">{{ section.label }}</Heading>
            <Text size="sm" tone="faint">{{ section.rows.length }} 项</Text>
            <span class="h-px flex-1 bg-line"></span>
          </div>

          <div class="grid min-w-0 gap-1.5 px-2 pr-1 sm:grid-cols-2 sm:px-3 sm:pr-2 2xl:grid-cols-3">
            <button
              v-for="row in section.rows"
              :key="row.key"
              type="button"
              :class="[
                'flex min-w-0 flex-col gap-2 rounded-card border bg-surface p-2 text-left transition-all',
                anyChosen(row)
                  ? 'border-accent bg-accent-soft shadow-sm'
                  : 'border-line hover:-translate-y-0.5 hover:border-accent/50 hover:shadow-sm',
              ]"
              @click="toggle(row)"
            >
              <!-- 这一格是谁:封面 + 名字。一个作品一张卡片,不同来源都在这张卡片里。 -->
              <div class="grid min-w-0 grid-cols-[2.75rem_minmax(0,1fr)] gap-2">
                <img
                  v-if="headOf(row)?.cover_url"
                  :src="headOf(row)?.cover_url"
                  alt=""
                  loading="lazy"
                  class="h-[3.75rem] w-11 shrink-0 rounded-control border border-line object-cover"
                />
                <span
                  v-else
                  class="h-[3.75rem] w-11 shrink-0 rounded-control border border-line bg-inset"
                ></span>

                <span class="flex min-w-0 flex-col justify-center gap-0.5">
                  <span class="line-clamp-2 text-sm font-medium leading-snug">{{ row.name }}</span>
                  <span v-if="headOf(row)?.original_title" class="truncate text-xs text-muted">
                    {{ headOf(row)?.original_title }}
                  </span>
                </span>
              </div>

              <span class="flex min-w-0 items-center justify-between gap-2 border-t border-line pt-1.5">
                <span class="truncate text-xs text-faint">
                  {{ row.items.map((item) => labelOfSource(item.source)).join(" · ") }}
                  <template v-if="headOf(row)?.year"> · {{ headOf(row)?.year }}</template>
                  <template v-if="headOf(row)?.kind"> · {{ headOf(row)?.kind }}</template>
                </span>
                <span
                  :class="[
                    'flex size-5 shrink-0 items-center justify-center rounded-full border text-xs font-medium',
                    anyChosen(row) ? 'border-accent bg-accent text-accent-on' : 'border-line text-muted',
                  ]"
                  aria-hidden="true"
                >{{ anyChosen(row) ? "✓" : "+" }}</span>
              </span>

              <span
                v-if="row.items.some((item) => claimOf(item))"
                class="text-xs text-muted"
              >
                已存在于《{{ row.items.map(claimOf).find(Boolean)?.work_title }}》
              </span>
            </button>
          </div>
        </div>
      </div>
    </div>

    <div v-if="hiddenCount" class="flex flex-wrap items-center gap-2">
      <Text size="sm" tone="muted">
        {{ rows.length ? "其余结果相关度较低。" : "没有找到高相关结果。" }}
      </Text>
      <Button size="sm" variant="ghost" @click="toggleOtherResults">
        {{ showAll ? "收起其余结果" : `查看其余 ${hiddenCount} 条` }}
      </Button>
    </div>

    <Text v-if="!props.candidates.length" size="sm" tone="muted">
      没有找到匹配结果。换个关键词,或者直接添加一件作品。
    </Text>

    <Text v-if="picked.length" size="sm" tone="muted">
      已选 {{ picked.length }} 个版本，完整信息会在下方生成并保持可编辑。
    </Text>
  </div>
</template>
