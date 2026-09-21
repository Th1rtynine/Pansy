<script setup lang="ts">
/**
 * 标签库:按媒体类型分成几段,一段一个类型的标签。
 *
 * 与作者库一样:只用来改与合并,不提供新建,也不提供删除。**同一个词在不同类型下
 * 是两条**,所以这里分段显示,而不是合成一张总表。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Alert, Center, Heading, Spinner, Tag, Text } from "../ui";

import { tags } from "../api";
import { mediaTypes } from "../mediaTypes";
import { useLoad, useReloadOnReturn } from "../useLoad";
import ListHeader from "../components/ListHeader.vue";

/** 这一页留在内存里(见 App.vue 的 KeepAlive 名单),两边要一致。 */
defineOptions({ name: "TagsList" });

const { data, error, loading, reload } = useLoad(() => tags.list());

// 退回来时先把原来那一屏显示出来,同时悄悄取一次新的(位置留住,数据不过期)。
useReloadOnReturn(() => void reload({ silent: true }));

const groups = computed(() =>
  mediaTypes.value.map((kind) => ({
    kind: kind.value,
    label: kind.label,
    items: (data.value ?? []).filter((tag) => tag.media_type === kind.value),
  })),
);
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到标签库">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-5">
    <ListHeader
      title="标签库"
      :note="`共 ${data.length} 个。`"
    />

    <section v-for="group in groups" :key="group.kind" class="flex flex-col gap-2">
      <Heading :level="2" size="lg">{{ group.label }}</Heading>
      <div v-if="group.items.length" class="flex flex-wrap gap-2">
        <RouterLink v-for="tag in group.items" :key="tag.id" :to="`/tags/${tag.id}`">
          <Tag variant="soft" tone="accent" size="md">
            {{ tag.name }}
            <Text size="sm" tone="muted">{{ tag.edition_count }}</Text>
          </Tag>
        </RouterLink>
      </div>
      <Text v-else size="sm" tone="faint">这个类型下还没有标签。</Text>
    </section>
  </div>
</template>
