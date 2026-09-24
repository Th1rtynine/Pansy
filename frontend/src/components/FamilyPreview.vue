<script setup lang="ts">
/**
 * 一族现在长什么样:该并进来的、该独立成另一部的、以及判不下来的。
 *
 * **名字不是归组的依据,关系才是** —— 所以每一行都带一句「凭什么」(后端算好的 `evidence`),
 * 人不看那句话就没法判断该不该勾。三块的默认状态也不同:同一作品默认勾,关联作品默认不勾,
 * 判不下来的既不勾也不丢,等人自己选。
 *
 * 它只负责画与勾选,**不管保存**:确认之后怎么落库由调用方决定。所以这里没有一个写请求。
 *
 * **不画 `confidence` 的数字**:后端只给 high / low / unknown 三档,画成百分比是在假装精确。
 */
import { computed, ref } from "vue";

import { Alert, Button, Heading, Tag, Text } from "../ui";
import { labelOf } from "../mediaTypes";
import { relationLabelOf } from "../relationNames";
import { labelOfSource } from "../sourceNames";
import type { FamilyMemberOut, FamilyPreviewOut } from "../types";

const props = withDefaults(
  defineProps<{
    preview: FamilyPreviewOut;
    /** 勾中的那些的键(`来源:外部id`),由调用方持有 —— 它才是要拿去导入的那一份。 */
    chosen?: string[];
  }>(),
  { chosen: () => [] },
);

const emit = defineEmits<{ toggle: [member: FamilyMemberOut] }>();

/** 一行认谁:来源加外部 id。**不用标题** —— 两个漫画版本标题一样,用标题当键会互相顶掉。 */
function memberKey(member: FamilyMemberOut): string {
  return `${member.candidate.source}:${member.candidate.external_id}`;
}

const isChosen = (member: FamilyMemberOut) => props.chosen.includes(memberKey(member));

/** 按类型分组,顺序照 `mediaTypes`(与「加入作品」其余地方同一套);认不出类型的归最后一组。 */
const groups = computed(() => {
  const order = ["light_novel", "manga", "anime", "game"];
  const found = new Map<string, FamilyMemberOut[]>();
  for (const member of props.preview.editions) {
    const media = member.candidate.media ?? "";
    found.set(media, [...(found.get(media) ?? []), member]);
  }
  return [...found.entries()]
    .map(([media, members]) => ({
      // 认不出类型时**照实说「类型未知」**,不硬塞进某一类:塞错了人就按错的类型建了。
      media,
      label: media ? labelOf(media) : "类型未知",
      members,
    }))
    .sort((left, right) => {
      const rank = (media: string) => (order.includes(media) ? order.indexOf(media) : order.length);
      return rank(left.media) - rank(right.media);
    });
});

/** 勾中的里面,有几条是要新建的(本地已有的是复用,不新建)。 */
const creating = computed(
  () =>
    props.preview.editions.filter((member) => isChosen(member) && !member.already_in_library).length,
);
const reusing = computed(
  () =>
    props.preview.editions.filter((member) => isChosen(member) && member.already_in_library).length,
);

const relatedChosen = computed(() =>
  props.preview.related_works.filter((member) => isChosen(member)).length,
);
const showRelated = ref(false);
const showUncertain = ref(false);
const uncertainChosen = computed(() =>
  props.preview.uncertain.filter((member) => isChosen(member)).length,
);

function noteOf(member: FamilyMemberOut): string {
  const parts = [labelOfSource(member.candidate.source)];
  if (member.candidate.year) parts.push(member.candidate.year);
  return parts.join(" · ");
}
</script>

<template>
  <div class="flex flex-col gap-4">
    <!-- 拿不到一部分时先说清楚:结果仍然可用,但人得知道少了什么。 -->
    <Alert v-for="warning in preview.warnings" :key="warning" tone="warning">{{ warning }}</Alert>

    <!-- 一、归入同一个统一作品 -->
    <section class="flex flex-col gap-2">
      <div class="flex flex-wrap items-baseline gap-2">
        <Heading :level="3" size="base">将归入《{{ preview.seed.title }}》</Heading>
        <Text size="sm" tone="faint">
          {{ creating }} 个版本<span v-if="reusing">，{{ reusing }} 个已在库中</span>
        </Text>
      </div>

      <div v-for="group in groups" :key="group.media || 'unknown'" class="flex flex-col gap-1">
        <Text size="sm" tone="muted">{{ group.label }}</Text>

        <label
          v-for="member in group.members"
          :key="memberKey(member)"
          :class="[
            'flex min-w-0 cursor-pointer items-start gap-2 rounded-control border p-2 transition-colors',
            isChosen(member) ? 'border-accent bg-accent-soft' : 'border-line',
          ]"
        >
          <input
            type="checkbox"
            class="mt-1 size-4 shrink-0 accent-accent"
            :checked="isChosen(member)"
            @change="emit('toggle', member)"
          />
          <img
            v-if="member.candidate.cover_url"
            :src="member.candidate.cover_url"
            alt=""
            loading="lazy"
            class="h-[3.75rem] w-11 shrink-0 rounded-control border border-line object-cover"
          />
          <span
            v-else
            class="h-[3.75rem] w-11 shrink-0 rounded-control border border-line bg-inset"
          ></span>

          <span class="flex min-w-0 flex-col gap-0.5">
            <span class="flex min-w-0 flex-wrap items-center gap-1.5">
              <span class="truncate text-sm font-medium">{{ member.candidate.title }}</span>
              <!-- 「已经在库里」必须显眼:不然人会以为又要建一件。 -->
              <Tag v-if="member.already_in_library" variant="soft" tone="neutral">已在库里</Tag>
            </span>
            <Text size="xs" tone="muted" class="truncate">{{ noteOf(member) }}</Text>
            <!-- **凭什么并进来的**:这一行是人做判断的依据,不能省。 -->
            <Text size="xs" tone="faint">{{ member.evidence }}</Text>
            <Text
              v-if="member.already_in_library && member.claimed_by"
              size="xs"
              tone="faint"
              class="truncate"
            >
              已记在《{{ member.claimed_by.work_title }}》的「{{
                member.claimed_by.edition_title || "未命名"
              }}」下
            </Text>
          </span>
        </label>
      </div>
    </section>

    <!-- 二、关联作品:显示但不并入 -->
    <section v-if="preview.related_works.length" class="flex flex-col gap-2 border-t border-line pt-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-baseline gap-2">
          <Heading :level="3" size="base">衍生与关联</Heading>
          <Text size="sm" tone="faint">
            {{ preview.related_works.length }} 部<span v-if="relatedChosen">，已选 {{ relatedChosen }} 部</span>
          </Text>
        </div>
        <Button size="sm" variant="ghost" @click="showRelated = !showRelated">
          {{ showRelated ? "收起" : "查看" }}
        </Button>
      </div>
      <Text size="sm" tone="muted">它们会单独建档，不会自动并入当前作品。</Text>

      <div v-if="showRelated" class="flex flex-col gap-1.5">
        <label
          v-for="member in preview.related_works"
          :key="memberKey(member)"
          :class="[
            'flex min-w-0 cursor-pointer items-center gap-2 rounded-control border p-2 transition-colors',
            isChosen(member) ? 'border-accent bg-accent-soft' : 'border-line',
          ]"
        >
          <input
            type="checkbox"
            class="size-4 shrink-0 accent-accent"
            :checked="isChosen(member)"
            @change="emit('toggle', member)"
          />
          <span class="flex min-w-0 flex-1 flex-col gap-0.5">
            <span class="flex min-w-0 flex-wrap items-center gap-1.5">
              <span class="truncate text-sm">{{ member.candidate.title }}</span>
              <!-- 它是主作品的什么:番外篇、外传、相同世界观…… **存的就是这个词**,所以直接画出来 -->
              <Tag variant="soft" tone="neutral">{{ relationLabelOf(member.relation_type) }}</Tag>
              <Tag v-if="member.already_in_library" variant="soft" tone="neutral">已在库里</Tag>
            </span>
            <Text size="xs" tone="faint">{{ member.evidence }}</Text>
          </span>
        </label>
      </div>
    </section>

    <!-- 三、需要确认:判不下来的 -->
    <section v-if="preview.uncertain.length" class="flex flex-col gap-2 border-t border-line pt-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div class="flex flex-wrap items-baseline gap-2">
          <Heading :level="3" size="base">需要确认</Heading>
          <Text size="sm" tone="faint">
            {{ preview.uncertain.length }} 条<span v-if="uncertainChosen">，已选 {{ uncertainChosen }} 条</span>
          </Text>
        </div>
        <Button size="sm" variant="ghost" @click="showUncertain = !showUncertain">
          {{ showUncertain ? "收起" : "查看" }}
        </Button>
      </div>
      <Text size="sm" tone="muted">这些内容没有自动加入；关系不够明确时，由你展开后决定。</Text>

      <label
        v-if="showUncertain"
        v-for="member in preview.uncertain"
        :key="memberKey(member)"
        :class="[
          'flex min-w-0 cursor-pointer items-center gap-2 rounded-control border p-2 transition-colors',
          isChosen(member) ? 'border-accent bg-accent-soft' : 'border-line',
        ]"
      >
        <input
          type="checkbox"
          class="size-4 shrink-0 accent-accent"
          :checked="isChosen(member)"
          @change="emit('toggle', member)"
        />
        <span class="flex min-w-0 flex-1 flex-col gap-0.5">
          <span class="truncate text-sm">{{ member.candidate.title }}</span>
          <Text size="xs" tone="faint">{{ member.evidence }}</Text>
        </span>
      </label>
    </section>

    <!-- 卷:只报个数。它们属于各自的 version,不去跟作品混在一起。 -->
    <Text v-if="preview.volumes.length" size="sm" tone="faint">
      顺带看到 {{ preview.volumes.length }} 卷(单行本一类),保存时挂到对应的版本下面。
    </Text>
  </div>
</template>
