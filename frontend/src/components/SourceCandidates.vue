<script setup lang="ts">
/**
 * 「用那个名字找到的这些,挑要加入的」那一块。**它不含输入框** —— 搜索入口在作品名那一格上(见 `pages/AddWork.vue`),
 * 这里只画候选、收勾选,再把勾中的每组报回页面。**按类型分段,同名的几条并排**:后端已认出「同一条记录」,
 * 并排的就是它在两个站上的样子,都勾上就都记住;**一个源在一组里最多勾一条**,分组只是建议,只有人自己敲的
 * ID(`resolved`)默认勾着。**一组一张卡片、卡片里各源各一行**,那片高度按两行写死(`min-h`),一排的下沿才齐。
 */
import { computed, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import { Heading, Text } from "../ui";

import { sources } from "../api";
import { labelOf, mediaTypes } from "../mediaTypes";
import { labelOfSource } from "../sourceNames";
import type { PickedCarrier, SourceCandidate } from "../types";

const props = withDefaults(
  defineProps<{
    candidates: SourceCandidate[];
    /** 人点名要的那一条(敲的是条目 ID 时才有):它默认勾着。 */
    resolved?: SourceCandidate | null;
  }>(),
  { resolved: null },
);

const emit = defineEmits<{ picks: [PickedCarrier[]] }>();

/** 一组同名候选:一条记录在两个站上的样子。 */
type Row = { key: string; media: string; name: string; items: SourceCandidate[] };

/** 勾中的:`组|源` → 那一条。一个源在一个组里最多一条。 */
const chosen = ref<Record<string, SourceCandidate>>({});
/** 勾中的那几条里**已经在库里的**是哪些。早问一句能省一整屏的力气:不加这一步,人要把整屏填完、点保存,才被那条唯一索引挡回来说「已经记在另一件作品上了」。 */
const claimed = ref<Record<string, { work_title: string; edition_id: number }>>({});

/**
 * 后端回的候选 → 按「类型 + 归一化名字」归组,顺序照它回来的顺序。同一个来源在一组里只能出现一次:两个同名的
 * Bangumi 条目可能是两个不同漫画版本(同一原作由不同作者改编),第二条必须另开一组,不能折成一个二选一。
 */
const rows = computed<Row[]>(() => {
  const out: Row[] = [];
  const buckets = new Map<string, Row[]>();
  for (const item of props.candidates) {
    const baseKey = `${item.media ?? ""}|${item.group}`;
    const bucket = buckets.get(baseKey) ?? [];
    const row = bucket.find(
      (candidate) => !candidate.items.some((member) => member.source === item.source),
    );
    if (row) {
      row.items.push(item);
    } else {
      const created: Row = {
        key: `${baseKey}|${bucket.length}`,
        media: item.media ?? "",
        name: item.title || item.original_title || item.external_id,
        items: [item],
      };
      bucket.push(created);
      buckets.set(baseKey, bucket);
      out.push(created);
    }
  }
  return out;
});

/** 再按类型分段:类型的顺序与全站一致(漫画、轻小说、Gal、动画),猜不出类型的排最后。 */
const sections = computed(() => {
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
        chosen.value = { [slotOf(row, resolved)]: resolved };
        void askClaim(resolved);
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

async function toggle(row: Row, item: SourceCandidate): Promise<void> {
  const slot = slotOf(row, item);
  const next = { ...chosen.value };
  if (isChosen(row, item)) {
    delete next[slot];
  } else {
    // 同一个源在同一个组里只留一条:库里一件作品在一个站上只对应一条。
    next[slot] = item;
  }
  chosen.value = next;
  announce();
  if (next[slot]) await askClaim(item);
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
  <div class="flex flex-col gap-4">
    <!-- 按类型分段:分野只是建议,勾哪一条由人定。 -->
    <div v-for="section in sections" :key="section.media" class="flex min-w-0 flex-col gap-2.5">
      <div class="flex items-center gap-2">
        <Heading :level="3" size="base">{{ section.label }}</Heading>
        <Text size="sm" tone="faint">{{ section.rows.length }} 组</Text>
        <span class="h-px flex-1 bg-line"></span>
      </div>

      <div class="grid min-w-0 gap-2 sm:grid-cols-2 2xl:grid-cols-3">
        <div
          v-for="row in section.rows"
          :key="row.key"
          :class="[
            'flex min-w-0 flex-col gap-2 rounded-card border p-2 transition-colors',
            anyChosen(row)
              ? 'border-accent bg-accent-soft shadow-sm'
              : 'border-line bg-surface',
          ]"
        >
          <!-- 这一格是谁:封面 + 名字。一个作品一张卡片,两个源都在这张卡片里。 -->
          <div class="grid min-w-0 grid-cols-[3.25rem_minmax(0,1fr)] gap-2.5">
            <img
              v-if="headOf(row)?.cover_url"
              :src="headOf(row)?.cover_url"
              alt=""
              loading="lazy"
              class="h-[4.5rem] w-[3.25rem] shrink-0 rounded-control border border-line object-cover"
            />
            <span
              v-else
              class="h-[4.5rem] w-[3.25rem] shrink-0 rounded-control border border-line bg-inset"
            ></span>

            <span class="flex min-w-0 flex-col justify-center gap-0.5">
              <span class="line-clamp-2 font-medium leading-snug">{{ row.name }}</span>
              <span v-if="headOf(row)?.original_title" class="truncate text-sm text-muted">
                {{ headOf(row)?.original_title }}
              </span>
            </span>
          </div>

          <!-- 各源各一行,点一行就是勾那一条。**这一个框的高度是写死的两行**:一个源的格子与两个源的格子一样高,同一排的下沿才对得齐。 -->
          <ul class="flex min-h-[3.75rem] min-w-0 flex-1 flex-col justify-center gap-1">
            <li v-for="item in row.items" :key="`${item.source}:${item.external_id}`" class="min-w-0">
              <button
                type="button"
                :class="[
                  'grid w-full min-w-0 grid-cols-[minmax(0,1fr)_1.5rem] items-center gap-2 rounded-control border px-2 py-1 text-left transition-colors',
                  isChosen(row, item)
                    ? 'border-accent bg-accent-soft'
                    : 'border-line bg-surface hover:border-accent/50 hover:bg-state-hover active:bg-state-press',
                ]"
                @click="toggle(row, item)"
              >
                <span class="flex min-w-0 flex-col gap-0.5">
                  <span class="truncate text-sm">{{ item.title || row.name }}</span>
                  <span class="flex flex-wrap items-center gap-x-1.5 text-xs text-faint">
                    <span>{{ labelOfSource(item.source) }} {{ item.external_id }}</span>
                    <span v-if="item.kind">{{ item.kind }}</span>
                    <span v-if="item.year">{{ item.year }}</span>
                  </span>
                </span>

                <span
                  :class="[
                    'flex size-6 items-center justify-center rounded-full border text-sm font-medium',
                    isChosen(row, item)
                      ? 'border-accent bg-accent text-accent-on'
                      : 'border-line text-muted',
                  ]"
                  aria-hidden="true"
                >
                  {{ isChosen(row, item) ? "✓" : "+" }}
                </span>
              </button>

              <!-- 已经在库里的先说一声,省得人填完一整屏才被挡回来。 -->
              <Text
                v-if="isChosen(row, item) && claimOf(item)"
                size="sm"
                tone="muted"
                class="mt-1 block px-1"
              >
                库里已经有这一条:
                <RouterLink class="text-accent-text" :to="`/editions/${claimOf(item)?.edition_id}`">
                  {{ claimOf(item)?.work_title }}
                </RouterLink>
              </Text>
            </li>
          </ul>
        </div>
      </div>
    </div>

    <Text v-if="!rows.length" size="sm" tone="muted">
      两个源里都没搜到这一部作品。换个写法再搜一次,或者直接自己填。
    </Text>

    <Text v-if="picked.length" size="sm" tone="muted">
      挑了 {{ picked.length }} 件,下面各有一份要填的;同一个名字下两个源都勾了,就一起记在这一件上。
    </Text>

    <Text size="sm" tone="faint">
      挑几件就有几份格子,不挑也行 —— 下面的格子本来就可以自己填。
    </Text>
  </div>
</template>
