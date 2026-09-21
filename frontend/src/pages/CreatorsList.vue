<script setup lang="ts">
/**
 * 作者库:一位一行。
 *
 * 这一页只用来改与合并 —— **不提供新建**(名字在作品表单里敲就建),也**不提供删除**
 * (作者是全库共用的词汇,删掉会连带抹掉引用)。所以它眼下没有入口,地址留着。
 */
import { RouterLink } from "vue-router";
import { Alert, Center, Heading, List, ListItem, Spinner, Text } from "../ui";

import { creators } from "../api";
import { useLoad, useReloadOnReturn } from "../useLoad";
import ListHeader from "../components/ListHeader.vue";

/** 这一页留在内存里(见 App.vue 的 KeepAlive 名单),两边要一致。 */
defineOptions({ name: "CreatorsList" });

const { data, error, loading, reload } = useLoad(() => creators.list());

// 退回来时先把原来那一屏显示出来,同时悄悄取一次新的(位置留住,数据不过期)。
useReloadOnReturn(() => void reload({ silent: true }));
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>
  <Alert v-else-if="error" tone="danger" title="读不到作者库">{{ error }}</Alert>

  <div v-else-if="data" class="flex flex-col gap-4">
    <ListHeader
      title="作者库"
      :note="`共 ${data.length} 位。`"
    />

    <List>
      <ListItem v-for="creator in data" :key="creator.id">
        <RouterLink
          class="flex flex-wrap items-baseline gap-x-3 rounded-control px-3 py-1 transition-colors hover:bg-state-hover focus-visible:bg-state-hover active:bg-state-press"
          :to="`/creators/${creator.id}`"
        >
          <Text size="base" weight="medium">{{ creator.name }}</Text>
          <Text size="sm" tone="muted">参与 {{ creator.edition_count }} 个作品</Text>
        </RouterLink>
      </ListItem>
    </List>
  </div>
</template>
