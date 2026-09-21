<script setup lang="ts">
/**
 * 一个标签:挂着它的全部作品。**没有「图 + 名」那种第一屏** —— 标签是一个词,配头像不成立,配作品封面更糟(会让人以为标签是作品)。
 * 标签名本身就是大标题(不装胶囊),类型与计数退到下面一行小字。
 */
import { computed } from "vue";
import { RouterLink, useRoute } from "vue-router";
import { Alert, Button, Center, Heading, Spinner, Text } from "../ui";

import { tags } from "../api";
import { useLoad } from "../useLoad";
import CarrierRow from "../components/CarrierRow.vue";

const route = useRoute();
const tagId = computed(() => Number(route.params.id));

const { data, error, loading } = useLoad(
  () => tags.get(tagId.value),
  () => route.fullPath,
);
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到这个标签">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-5">
    <div class="flex flex-wrap items-end justify-between gap-3 border-b border-line pb-4">
      <div class="flex min-w-0 flex-col gap-1">
        <Heading :level="1" size="2xl">{{ data.name }}</Heading>
        <Text size="sm" tone="muted">
          {{ data.media_label }}的标签 ·
          {{ data.editions.length ? `${data.editions.length} 份作品` : "还没有作品用它" }}
        </Text>
      </div>
      <RouterLink :to="`/tags/${data.id}/edit`">
        <Button variant="outline" size="sm">编辑</Button>
      </RouterLink>
    </div>

    <ul v-if="data.editions.length" class="flex flex-col divide-y divide-line">
      <CarrierRow v-for="edition in data.editions" :key="edition.id" :edition="edition" />
    </ul>
    <Text v-else size="sm" tone="muted">暂无作品用这个标签。</Text>

    <Text size="sm">
      <RouterLink class="text-accent-text" to="/works">← 回到列表</RouterLink>
    </Text>
  </div>
</template>
