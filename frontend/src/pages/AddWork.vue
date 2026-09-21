<script setup lang="ts">
/**
 * 加入作品:从外部来源找载体、审核「总标题 + 每一份载体」的草稿,再一次保存(`POST /api/works/with-editions`,一个事务,失败就什么都没有 —— 分几次发会留下没有作品的空总标题)。
 * **搜索词不是作品资料**:简称、编号或链接不该偷偷变成正式标题,所以顶上独立一个搜索框,总标题、原名与别名只在选中候选后由完整条目补入,也始终可改。
 * **总标题不再等于最早点击的载体**:后端沿来源的原作关系找作品身份(动画「某某 第二季」的总标题可取自关联的原作书籍,`edition.title` 仍保留它自己的),关系不可靠时才用候选本身。
 * **一部作品本来就是漫画、轻小说、Gal、动画各一条**,所以一次建出「总标题 + N 件」共用一个总标题;**预填只是草稿** —— 外部内容只落进格子给人过目,每格底下写着是谁给的、点得回去。
 */
import { computed, reactive, ref } from "vue";
import { useRouter } from "vue-router";
import { Alert, Button, FormField, Input, SegmentedControl, Spinner, TagsInput, Text } from "../ui";

import { sources, works } from "../api";
import { fieldsOf, labelOf, mediaTypes } from "../mediaTypes";
import { applySuggestions, coverFrom, sourcesOf, TAG_TAKE } from "../prefill";
import { labelOfSource } from "../sourceNames";
import { messageOf } from "../useLoad";
import { useUnsavedChanges } from "../useUnsavedChanges";
import type {
  CollectOut,
  EditionIn,
  PickedCarrier,
  SourceCandidate,
  SourceIdentityOut,
  SourceSuggestion,
  WorkIn,
} from "../types";
import CarrierFields from "../components/CarrierFields.vue";
import FormPage from "../components/FormPage.vue";
import FormSection from "../components/FormSection.vue";
import SourceCandidates from "../components/SourceCandidates.vue";
import WorkEditNav from "../components/WorkEditNav.vue";

const router = useRouter();

/** 页面上的一份表单:一件作品,连同它是从哪几条候选来的。 */
type Draft = {
  /** 那一组候选的名字(或者自己填的那一件的编号);靠它认出「还是刚才那一份」。 */
  key: string;
  picks: SourceCandidate[];
  edition: EditionIn;
  suggestions: SourceSuggestion[];
  /** 已经按哪几条候选取过建议了 —— 没变就不重复取。 */
  stamp: string;
  coverUrl: string;
  keepCover: boolean;
  skippedTags: number;
  identity: SourceIdentityOut | null;
  /**
   * 这一件底下的卷(选中一条**系列**条目时从源里读回来的草稿)。**列在这里、保存前能改** —— 卷不是候选,不该跟候选一起搜出来;
   * 但选中之后有几卷、每卷叫什么、什么时候出的,都要在保存之前过目。
   */
  volumes: VolumeDraft[];
};

type VolumeDraft = {
  key: string;
  volume_number: number | null;
  title: string;
  published_on: string;
  cover_url: string;
};

function emptyCarrier(mediaType: string): EditionIn {
  return {
    media_type: mediaType,
    title: "",
    published_on: "",
    summary: "",
    org: "",
    release_status: "",
    volume_count: null,
    creators: [],
    tags: [],
  };
}

function makeDraft(carrier: PickedCarrier): Draft {
  return {
    key: carrier.key,
    picks: carrier.items,
    edition: emptyCarrier(carrier.media),
    suggestions: [],
    stamp: "",
    coverUrl: "",
    keepCover: true,
    skippedTags: 0,
    identity: null,
    volumes: [],
  };
}

const workForm = ref<WorkIn>({ title: "", original_title: "", aliases: [] });
const drafts = ref<Draft[]>([]);
const activePanel = ref("work");
const selfCount = ref(0);
const choosingManualType = ref(false);

const error = ref("");
const saving = ref(false);
const filling = ref(0);

const found = ref<CollectOut | null>(null);
const looking = ref(false);
const searchText = ref("");
const searched = ref(false);
const workIdentity = ref<SourceIdentityOut | null>(null);
const workSuggestions = ref<SourceSuggestion[]>([]);
const workIdentityStamp = ref("");
/** 人碰过的正式字段不再被后续自动发现覆盖。 */
const workTouched = reactive({ title: false, original_title: false, aliases: false });

function formSnapshot(): string {
  return JSON.stringify({
    work: workForm.value,
    editions: drafts.value.map((draft) => ({
      key: draft.key,
      picks: draft.picks.map((item) => `${item.source}:${item.external_id}`),
      edition: draft.edition,
      coverUrl: draft.coverUrl,
      keepCover: draft.keepCover,
    })),
  });
}

const savedSnapshot = ref(formSnapshot());
const isDirty = computed(() => formSnapshot() !== savedSnapshot.value);
useUnsavedChanges(isDirty);

const typeOptions = computed(() =>
  mediaTypes.value.map((item) => ({ value: item.value, label: item.label })),
);
const firstSuggestions = computed(() => workSuggestions.value);
const activeDraft = computed(() =>
  drafts.value.find((draft) => draft.key === activePanel.value) ?? null,
);
const identityConflict = computed(() => {
  const keys = new Set(
    drafts.value
      .map((draft) => draft.identity?.work)
      .filter((item): item is SourceCandidate => Boolean(item))
      .map(nameOf),
  );
  return keys.size > 1;
});

function draftLabel(draft: Draft): string {
  return draft.edition.media_type ? labelOf(draft.edition.media_type) : "类型待定";
}

function draftName(draft: Draft): string {
  const title = draft.edition.title.trim() || draft.picks[0]?.title || "尚未填写标题";
  const names = [
    ...new Set(draft.edition.creators.map((creator) => creator.name.trim()).filter(Boolean)),
  ];
  if (!names.length) return title;
  const shown = names.slice(0, 2).join("、");
  return `${title} · ${shown}${names.length > 2 ? " 等" : ""}`;
}

const navItems = computed(() => [
  {
    key: "work",
    label: "作品信息",
    detail: workForm.value.title || "总标题与别名",
    done: Boolean(workForm.value.title.trim()),
  },
  ...drafts.value.map((draft) => ({
    key: draft.key,
    label: draftLabel(draft),
    detail: draftName(draft),
    done: Boolean(draft.edition.media_type),
  })),
]);

/**
 * 搜索框接受名字、Bangumi 编号、带前缀的编号或条目链接;搜索文字只活在搜索区,不会写进正式作品字段。按精确编号找到的条目由候选组件默认选中。
 */
async function look(text: string): Promise<void> {
  const keyword = text.trim();
  if (!keyword) return;

  looking.value = true;
  error.value = "";
  try {
    const answer = await sources.collect(keyword);
    found.value = answer;
    searched.value = true;
  } catch (failure) {
    found.value = null;
    error.value = messageOf(failure);
  } finally {
    looking.value = false;
  }
}

/** 「用了这些词」那一行:**按词合并**,同一个词搜了哪几个源一起说。 */
const stepLine = computed(() => {
  const byKeyword = new Map<string, string[]>();
  for (const step of found.value?.steps ?? []) {
    byKeyword.set(step.keyword, [...(byKeyword.get(step.keyword) ?? []), labelOfSource(step.source)]);
  }
  return [...byKeyword]
    .map(([keyword, names]) => `${names.join("、")}「${keyword}」`)
    .join(";");
});

function fromWhom(field: string): string {
  const names = sourcesOf(firstSuggestions.value, field);
  return names.length ? `来自 ${names.join("、")}` : "";
}

function sourceLink(field: string): string {
  return firstSuggestions.value.find((item) => item.field === field)?.url ?? "";
}

function specOf(draft: Draft): Record<string, string> {
  return fieldsOf(draft.edition.media_type);
}

/**
 * 换类型**只清掉跟着类型走的那两项**(状态与数量):名字、简介、作者、标签跨类型共用,清掉等于白填一遍;而「连载中」这种状态换类型就是错的。
 */
function chooseType(draft: Draft, value: string | number): void {
  const next = String(value);
  if (next === draft.edition.media_type) return;
  draft.edition = {
    ...draft.edition,
    media_type: next,
    release_status: "",
    volume_count: null,
  };
}

function addSelf(mediaType: string): void {
  selfCount.value += 1;
  const created: Draft = {
    key: `self-${selfCount.value}`,
    picks: [],
    edition: emptyCarrier(mediaType),
    suggestions: [],
    stamp: "",
    coverUrl: "",
    keepCover: true,
    skippedTags: 0,
    identity: null,
    volumes: [],
  };
  drafts.value = [
    ...drafts.value,
    created,
  ];
  activePanel.value = created.key;
  choosingManualType.value = false;
}

/**
 * 选中了**系列**条目的那几件:问它底下有哪些卷,列在表单里给人过目、改。**一人一次**:已经有卷的那一份不再问(改过的东西不能被重新盖掉);
 * 分不出「系列 / 卷」的源回空表,那就没有卷可列 —— 卷仍然可以在作品页上手工加。
 */
async function fillVolumes(): Promise<void> {
  await Promise.all(
    drafts.value.map(async (draft) => {
      const series = draft.picks.find((item) => item.series);
      if (!series || draft.volumes.length) return;
      const found = await sources.volumes(series.source, series.external_id);
      draft.volumes = found.map((volume, index) => ({
        key: `${series.source}-${volume.external_id}-${index}`,
        volume_number: volume.number,
        title: volume.title ?? "",
        published_on: volume.published_on ?? "",
        cover_url: volume.cover_url ?? "",
      }));
    }),
  );
}

function drop(key: string): void {  drafts.value = drafts.value.filter((draft) => draft.key !== key);
  if (activePanel.value === key) activePanel.value = "work";
  void refreshWorkIdentity();
}

/** 上面挑了哪几件 → 下面就有哪几份表单。**已经填过的不会被清掉**(按 key 认)。 */
function onPicks(carriers: PickedCarrier[]): void {
  const existing = new Map(drafts.value.map((draft) => [draft.key, draft]));
  // 自己填的那几件不在候选里,所以每次重排都把它们原样留在后面。
  const selves = drafts.value.filter((draft) => draft.key.startsWith("self-"));
  drafts.value = [
    ...carriers.map((carrier) => {
      const draft = existing.get(carrier.key);
      if (!draft) return makeDraft(carrier);
      // 同一组里多勾了一个源(或者换了一条):候选换了,建议要重取。
      if (draft.picks.map(nameOf).join() !== carrier.items.map(nameOf).join()) {
        draft.stamp = "";
        draft.identity = null;
        draft.volumes = [];
      }
      draft.picks = carrier.items;
      return draft;
    }),
    ...selves,
  ];
  if (activePanel.value !== "work" && !drafts.value.some((draft) => draft.key === activePanel.value)) {
    activePanel.value = "work";
  }
  void fillAll();
  // 卷单独问一次:它是「这一部底下有几卷」,与逐字段建议不是一回事(也不再问第二遍)。
  void fillVolumes();
}

function nameOf(item: SourceCandidate): string {
  return `${item.source}:${item.external_id}`;
}

/** 每件各取各的建议,同时问清它属于哪个原作总标题。 */
async function fillAll(): Promise<void> {
  const wanted = drafts.value
    .filter((draft) => draft.picks.length)
    .map((draft) => [draft, draft.picks.map(nameOf).join()] as const)
    .filter(([draft, stamp]) => draft.stamp !== stamp);
  if (!wanted.length) {
    await refreshWorkIdentity();
    return;
  }

  filling.value += wanted.length;
  try {
    await Promise.all(
      wanted.map(async ([draft, stamp]) => {
        draft.stamp = stamp;
        const identityPick =
          draft.picks.find((item) => item.source === "bangumi") ?? draft.picks[0];
        const [suggestions, identity] = await Promise.all([
          sources.suggest(
            draft.picks.map((item) => ({ source: item.source, external_id: item.external_id })),
          ),
          sources
            .identity(identityPick.source, identityPick.external_id)
            .catch(() => ({ work: identityPick, relations: [] })),
        ]);
        // 人在请求途中又换了候选时,旧响应不能回头覆盖新草稿。
        if (draft.stamp !== stamp || !drafts.value.includes(draft)) return;
        draft.suggestions = suggestions;
        draft.identity = identity;
        // 这里只填载体。总标题由所有已选载体的 identity 一起决定,与点击顺序无关。
        const result = applySuggestions(suggestions, {
          work: null,
          edition: draft.edition,
        });
        draft.skippedTags = result.skippedTags;
        if (!draft.coverUrl) draft.coverUrl = coverFrom(suggestions);
      }),
    );
    await refreshWorkIdentity();
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    filling.value = 0;
  }
}

/**
 * 汇总每一份载体找到的作品身份。多数一致的优先;票数相同时,沿关系找到的原作优先于「就用载体自己」——
 * 这样后选的漫画可以和先选的动画共同指向同一原作,不必把 `drafts[0]` 当成一条隐藏规则。
 */
async function refreshWorkIdentity(): Promise<void> {
  const groups = new Map<
    string,
    { identity: SourceIdentityOut; count: number; discovered: boolean; order: number }
  >();
  drafts.value.forEach((draft, order) => {
    if (!draft.identity) return;
    const key = nameOf(draft.identity.work);
    const old = groups.get(key);
    if (old) {
      old.count += 1;
      old.discovered ||= draft.identity.relations.length > 0;
    } else {
      groups.set(key, {
        identity: draft.identity,
        count: 1,
        discovered: draft.identity.relations.length > 0,
        order,
      });
    }
  });

  const chosen = [...groups.values()].sort(
    (left, right) =>
      right.count - left.count ||
      Number(right.discovered) - Number(left.discovered) ||
      left.order - right.order,
  )[0];

  if (!chosen) {
    workIdentity.value = null;
    workSuggestions.value = [];
    workIdentityStamp.value = "";
    if (!workTouched.title) workForm.value.title = "";
    if (!workTouched.original_title) workForm.value.original_title = "";
    if (!workTouched.aliases) workForm.value.aliases = [];
    return;
  }

  const identity = chosen.identity;
  const stamp = nameOf(identity.work);
  workIdentity.value = identity;
  if (workIdentityStamp.value === stamp) return;

  const suggestions = await sources.suggest([
    { source: identity.work.source, external_id: identity.work.external_id },
  ]);
  // 完整条目还在路上时,人可能已经换了一条身份:认出来的不再是它就作废。
  const stillChosen = [...drafts.value]
    .map((draft) => draft.identity)
    .filter((item): item is SourceIdentityOut => Boolean(item))
    .some((item) => nameOf(item.work) === stamp);
  if (!stillChosen) return;

  const proposed: WorkIn = { title: "", original_title: "", aliases: [] };
  applySuggestions(suggestions, { work: proposed, edition: emptyCarrier("") });
  if (!proposed.title) proposed.title = identity.work.title || identity.work.original_title || "";
  if (!proposed.original_title) proposed.original_title = identity.work.original_title ?? "";
  proposed.aliases = [
    ...new Set([...proposed.aliases, ...identity.work.aliases]),
  ].filter((name) => name && name !== proposed.title && name !== proposed.original_title);

  if (!workTouched.title) workForm.value.title = proposed.title;
  if (!workTouched.original_title) workForm.value.original_title = proposed.original_title;
  if (!workTouched.aliases) workForm.value.aliases = proposed.aliases;
  workSuggestions.value = suggestions;
  workIdentityStamp.value = stamp;
}

async function save(): Promise<void> {
  error.value = "";
  if (!workForm.value.title.trim()) {
    error.value = "作品总标题还没填。";
    activePanel.value = "work";
    return;
  }
  if (!drafts.value.length) {
    error.value = "还没有要加入的东西 —— 在上面挑一条,或者点「自己填一件」。";
    return;
  }
  const nameless = drafts.value.findIndex((draft) => !draft.edition.media_type);
  if (nameless >= 0) {
    error.value = `第 ${nameless + 1} 件还没有选类型 —— 类型定了就不能改,所以要你自己点一下。`;
    activePanel.value = drafts.value[nameless].key;
    return;
  }

  saving.value = true;
  try {
    const created = await works.createWithEditions({
      work: workForm.value,
      // 总标题自己的封面 = **原作那一条的图**(填总标题那三个字段用的那一条),一次保存里顺手取回;
      // 认不出身份时留空 —— 那一部照样建起来,页面上看到的是第一件的封面。
      work_cover_url: workIdentity.value?.work.cover_url ?? "",
      editions: drafts.value.map((draft) => ({
        ...draft.edition,
        refs: draft.picks.map((item) => ({
          source: item.source,
          external_id: item.external_id,
          title: item.title,
        })),
        cover_url: draft.keepCover && draft.coverUrl ? draft.coverUrl : undefined,
        // 卷:页面上列出来的那一份就是最终要写进去的(卷号、名字、发售日、封面外链)。
        // 一卷都没有就是空表,后端不写卷。
        volumes: draft.volumes.map((volume) => ({
          volume_number: volume.volume_number,
          title: volume.title.trim(),
          summary: "",
          published_on: volume.published_on.trim(),
          cover_url: volume.cover_url || undefined,
        })),
      })),
    });
    savedSnapshot.value = formSnapshot();
    router.push(
      created.editions.length === 1 ? `/editions/${created.editions[0].id}` : `/works/${created.id}`,
    );
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <FormPage
    submit-label="加入"
    :saving="saving"
    cancel-to="/works"
    @submit="save"
  >
    <template #alerts>
      <Alert v-if="error" tone="danger" title="没能加入">{{ error }}</Alert>
    </template>

    <FormSection
      title="从 Bangumi 查找"
      description="搜索词只用来查找,不会写进作品资料。支持作品名、Bangumi 编号、bgm:编号或条目链接。"
    >
      <FormField>
        <div class="grid gap-2 sm:grid-cols-[minmax(0,1fr)_auto]">
          <Input
            v-model="searchText"
            placeholder="例如:咒术回战、294993 或 Bangumi 条目链接"
            autocomplete="off"
            @keydown.enter.prevent="look(searchText)"
          />
          <Button
            type="button"
            variant="solid"
            tone="accent"
            :loading="looking"
            :disabled="looking || !searchText.trim()"
            class="w-full sm:w-auto"
            @click="look(searchText)"
          >
            搜索 Bangumi
          </Button>
        </div>
        <Text size="sm" tone="faint">
          一到三位纯数字仍按作品名搜索;四位以上纯数字按 Bangumi 编号读取。
        </Text>
        <Text v-if="stepLine" size="sm" tone="faint">本次使用:{{ stepLine }}</Text>
      </FormField>
    </FormSection>

    <FormSection
      v-if="searched"
      title="选择要加入的版本"
      description="可以同时选择漫画、轻小说、动画或游戏。选中后会读取完整资料,并尝试找到它的原作总标题。"
    >
      <SourceCandidates
        :candidates="found?.candidates ?? []"
        :resolved="found?.resolved ?? null"
        @picks="onPicks"
      />
    </FormSection>

    <div class="grid min-w-0 gap-4 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start lg:gap-5">
      <WorkEditNav
        :items="navItems"
        :active="activePanel"
        @select="activePanel = $event"
        @add="choosingManualType = !choosingManualType"
      >
        <template #after-add>
          <div
            v-if="choosingManualType"
            class="grid min-w-56 grid-cols-2 gap-1 rounded-control bg-inset p-1.5 lg:min-w-0"
          >
            <button
              v-for="option in typeOptions"
              :key="option.value"
              type="button"
              class="rounded-control px-2 py-1.5 text-sm text-fg transition-colors hover:bg-surface hover:text-accent-text"
              @click="addSelf(String(option.value))"
            >
              {{ option.label }}
            </button>
          </div>
        </template>
      </WorkEditNav>

      <div class="min-w-0">
        <template v-if="activePanel === 'work'">
          <FormSection
            title="作品信息"
            description="这一层描述共同的原作;动画、漫画等版本保留各自的标题与资料。"
          >
            <Alert v-if="identityConflict" tone="warning" title="发现多个作品依据">
              选中的条目没有全部指向同一个原作。当前采用关联最多的一条,请核对下面三个字段。
            </Alert>

            <div
              v-if="workIdentity"
              class="flex flex-col gap-1 rounded-card border border-accent/30 bg-accent-soft px-3 py-2 sm:flex-row sm:items-center sm:justify-between"
            >
              <div class="min-w-0">
                <Text size="sm" tone="muted">总标题依据</Text>
                <div class="truncate font-medium text-accent-text">
                  {{ workIdentity.work.title || workIdentity.work.original_title }}
                </div>
              </div>
              <Text size="sm" tone="muted" class="shrink-0">
                {{ labelOfSource(workIdentity.work.source) }} {{ workIdentity.work.external_id }}
                <template v-if="workIdentity.relations.length">
                  · 经 {{ workIdentity.relations.join(" → ") }} 找到原作
                </template>
                <template v-else> · 当前条目</template>
              </Text>
            </div>

            <FormField label="作品总标题" required description="整部作品共用的标题,可以修改自动结果">
              <Input
                v-model="workForm.title"
                placeholder="选中候选后自动填写,也可以自己输入"
                @update:model-value="workTouched.title = true"
              />
              <Text v-if="fromWhom('title') || fromWhom('original_title')" size="sm" tone="faint">
                {{ fromWhom("title") || fromWhom("original_title") }}
                <a
                  v-if="sourceLink('title') || sourceLink('original_title')"
                  class="text-accent-text"
                  :href="sourceLink('title') || sourceLink('original_title')"
                  target="_blank"
                  rel="noreferrer"
                >
                  看原文
                </a>
              </Text>
            </FormField>

            <FormField label="原名" description="原作使用的原文标题">
              <Input
                v-model="workForm.original_title"
                @update:model-value="workTouched.original_title = true"
              />
              <Text v-if="fromWhom('original_title')" size="sm" tone="faint">
                {{ fromWhom("original_title") }}
              </Text>
            </FormField>

            <FormField label="别名" description="选中候选后从完整条目读取;输入后按回车添加">
              <TagsInput
                v-model="workForm.aliases"
                @update:model-value="workTouched.aliases = true"
              />
              <Text v-if="fromWhom('alias')" size="sm" tone="faint">{{ fromWhom("alias") }}</Text>
            </FormField>
          </FormSection>

          <Text size="sm" tone="faint">
            没被 Bangumi 收录的内容,可以在上方层级栏点「添加作品」后自己填写。
          </Text>
        </template>

        <FormSection
          v-else-if="activeDraft"
          :title="`${draftLabel(activeDraft)} · ${draftName(activeDraft)}`"
          :description="
            activeDraft.picks.length
              ? `来自 ${activeDraft.picks.map((item) => `${labelOfSource(item.source)} ${item.external_id}`).join('、')}`
              : '自己填写的这一份作品,不从外部来源取内容。'
          "
        >
          <FormField label="类型" description="必填,建好之后不能改;换类型会清掉状态与数量" required>
            <SegmentedControl
              :model-value="activeDraft.edition.media_type"
              :options="typeOptions"
              @update:model-value="(value) => chooseType(activeDraft, value)"
            />
          </FormField>

          <CarrierFields v-model="activeDraft.edition" :spec="specOf(activeDraft)" />

          <Text v-if="activeDraft.skippedTags" size="sm" tone="faint">
            标签先填了 {{ TAG_TAKE }} 个,还有 {{ activeDraft.skippedTags }} 个没填 —— 需要的话在这一份作品自己的页面上加。
          </Text>

          <div v-if="activeDraft.coverUrl" class="flex items-start gap-3 border-t border-line pt-4">
            <img
              :src="activeDraft.coverUrl"
              alt=""
              class="h-40 w-30 shrink-0 rounded-card border border-line object-cover"
            />
            <div class="flex flex-col gap-2">
              <Text size="sm" tone="muted">外部源给的那一张。保存时先把它存到本机,再写进库里。</Text>
              <label class="flex items-center gap-2 text-base">
                <input v-model="activeDraft.keepCover" type="checkbox" />
                保存时一起存下来
              </label>
              <Button variant="soft" size="sm" @click="activeDraft.coverUrl = ''">不用这一张</Button>
            </div>
          </div>

          <!-- 卷:选中一条**系列**条目时从源里读回来的那一份,列在这里过目、改 —— 少一卷就删掉,名字不对就改写,自己也能加一行。 -->
          <div v-if="activeDraft.volumes.length" class="flex flex-col gap-2 border-t border-line pt-4">
            <div class="flex flex-wrap items-center gap-2">
              <Text size="sm" tone="muted">
                这一部底下有 {{ activeDraft.volumes.length }} 卷,保存时跟着这一件一起记下来。不要的可以删,名字与日期都能改。
              </Text>
            </div>
            <ul class="flex flex-col gap-1.5">
              <li
                v-for="volume in activeDraft.volumes"
                :key="volume.key"
                class="grid grid-cols-[4.5rem_minmax(0,1fr)_9rem_2rem] items-center gap-2"
              >
                <Input v-model="volume.volume_number" type="number" step="0.5" placeholder="卷号" />
                <Input v-model="volume.title" placeholder="这一卷的名字" />
                <Input v-model="volume.published_on" placeholder="发售日" />
                <Button
                  variant="ghost"
                  size="sm"
                  :aria-label="`删掉第 ${volume.volume_number ?? '?'} 卷`"
                  @click="activeDraft.volumes = activeDraft.volumes.filter((row) => row.key !== volume.key)"
                >
                  ×
                </Button>
              </li>
            </ul>
            <div>
              <Button
                variant="soft"
                size="sm"
                @click="
                  activeDraft.volumes = [
                    ...activeDraft.volumes,
                    {
                      key: `own-${activeDraft.key}-${activeDraft.volumes.length}`,
                      volume_number: null,
                      title: '',
                      published_on: '',
                      cover_url: '',
                    },
                  ]
                "
              >
                ＋ 自己加一卷
              </Button>
            </div>
          </div>

          <div class="flex flex-wrap items-center gap-2">
            <Button variant="ghost" tone="danger" size="sm" @click="drop(activeDraft.key)">
              {{ activeDraft.picks.length ? "不加入这一份" : "去掉这一份" }}
            </Button>
          </div>
        </FormSection>

        <div v-if="filling" class="flex items-center gap-2 py-2">
          <Spinner size="sm" />
          <Text size="sm" tone="faint">正在读取完整条目并寻找原作…</Text>
        </div>
        <Text v-else-if="activePanel !== 'work' && !activeDraft" size="sm" tone="faint">
          这一份作品已经移除,请从左侧选择其它内容。
        </Text>
      </div>
    </div>
  </FormPage>
</template>
