<script setup lang="ts">
/**
 * 一份作品自己的内容:它是什么、说了什么、谁做的、挂着什么、收录了哪些卷,只读 —— 改东西去编辑页。
 *
 * 只给作品自己的页用(`/editions/:id`);总标题页上是一张卡片(CarrierCard.vue)。排法是左右两列(左读右查),
 * 窄屏右列落到下面。「哪几项、叫什么」问 `fields`(后端 MEDIA_TYPE_FIELDS):不记的项整段不出现。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Heading, Tag, Text } from "../ui";

import InfoPanel from "./InfoPanel.vue";
import VolumeCard from "./VolumeCard.vue";
import type { EditionOut } from "../types";

const props = defineProps<{ edition: EditionOut }>();

const fields = computed(() => props.edition.fields);

/** 按角色分组:同一个人可能在一份作品里担两样。 */
const byRole = computed(() => {
  const groups = new Map<string, { id: number; name: string }[]>();
  for (const creator of props.edition.creators) {
    const people = groups.get(creator.role) ?? [];
    people.push({ id: creator.id, name: creator.name });
    groups.set(creator.role, people);
  }
  return [...groups.entries()];
});

const volumeWord = computed(() => props.edition.fields.unit || "卷");

/** 右边那张表:每一项都是「要查的短值」,并把计数单列出来。 */
const panelRows = computed(() => {
  const edition = props.edition;
  const rows: { label: string; value: string }[] = [];
  const push = (label: string | undefined, value: string | number | null) => {
    if (label) rows.push({ label, value: value === null || value === "" ? "—" : String(value) });
  };
  push(fields.value.time, edition.published_on);
  push(fields.value.org, edition.org);
  push(fields.value.status, edition.release_status);
  push(fields.value.count, edition.volume_count);
  if (edition.volumes.length) push(`收录${volumeWord.value}`, edition.volumes.length);
  if (edition.creators.length) push("作者", `${edition.creators.length} 位`);
  if (edition.tags.length) push("标签", `${edition.tags.length} 个`);
  return rows;
});
</script>

<template>
  <div class="flex flex-col gap-5 lg:flex-row lg:gap-8">
    <div class="flex min-w-0 flex-1 flex-col gap-3">
      <Text as="p">{{ edition.summary || "—" }}</Text>

      <Text size="sm" tone="muted">
        <template v-if="byRole.length">
          <template v-for="([role, people], index) in byRole" :key="role">
            <span v-if="index"> · </span>{{ role }}
            <template v-for="(person, position) in people" :key="person.id">
              <RouterLink class="text-accent-text" :to="`/creators/${person.id}`">
                {{ person.name }}
              </RouterLink>
              <span v-if="position < people.length - 1">、</span>
            </template>
          </template>
        </template>
        <template v-else>暂无作者</template>
      </Text>

      <!-- 分类标签:字号 `sm`(13px)、**字重回到 400** —— **不要再加 `font-medium` 之类的类**,13px 的中文配可变字体插值出来的 500 会糊,理由写在 Tag.vue 里。 -->
      <div v-if="edition.tags.length" class="flex flex-wrap gap-2">
        <RouterLink v-for="tag in edition.tags" :key="tag.id" :to="`/tags/${tag.id}`">
          <Tag variant="soft" tone="accent" size="sm">{{ tag.name }}</Tag>
        </RouterLink>
      </div>

      <!-- 卷这一段是**封面卡片网格**,不是一行行文字:一整套漫画几乎每卷没有名字,密度也有意压过(一行三到五张)。 -->
      <div v-if="edition.volumes.length" class="flex flex-col gap-3">
        <Heading :level="2" size="sm">{{ volumeWord }} ({{ edition.volumes.length }})</Heading>
        <div class="grid grid-cols-3 gap-2.5 sm:grid-cols-4 lg:grid-cols-5">
          <VolumeCard
            v-for="volume in edition.volumes"
            :key="volume.id"
            :volume="volume"
            :unit="edition.fields.unit"
          />
        </div>
      </div>
      <Text v-else-if="fields.unit" size="sm" tone="faint">暂无{{ volumeWord }}。</Text>
    </div>

    <div class="shrink-0 lg:w-64">
      <InfoPanel :rows="panelRows">
        <RouterLink class="text-sm text-accent-text" :to="`/works/${edition.work_id}`">
          回到《{{ edition.work_title }}》 →
        </RouterLink>
      </InfoPanel>
    </div>
  </div>
</template>
