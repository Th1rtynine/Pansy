<script setup lang="ts">
/**
 * 未连接数据源时出现的轻量引导。获取凭据是准备动作，不该和账号状态抢视觉重心；
 * 因此这里只留一句说明和一个直达官方页面的按钮，连接成功后由父页面移除整个组件。
 */
import { Button, Text } from "../ui";
import { openExternal } from "../openExternal";

const props = defineProps<{
  title: string;
  description: string;
  action: string;
  href: string;
}>();

async function openOfficialPage(): Promise<void> {
  await openExternal(props.href);
}
</script>

<template>
  <div
    class="flex flex-col gap-3 rounded-card border border-line bg-subtle p-4 sm:flex-row sm:items-center sm:justify-between"
  >
    <div class="flex min-w-0 flex-col gap-0.5">
      <Text size="sm" weight="medium">{{ title }}</Text>
      <Text size="xs" tone="muted">{{ description }}</Text>
    </div>
    <Button class="shrink-0" size="sm" variant="soft" tone="accent" @click="openOfficialPage">
      {{ action }}
    </Button>
  </div>
</template>
