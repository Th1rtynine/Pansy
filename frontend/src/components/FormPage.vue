<script setup lang="ts">
/**
 * 表单页的外壳:页头、提示区、字段区、底部那条动作;五个表单页(作品总标题、作品、卷、作者、标签)共用这一层,
 * 标题层级、间距、保存按钮的位置才不会各不相同,页面自己只管默认插槽里的字段。四个插槽:`alerts` 在字段区上面
 * (读不到这一条、保存失败都要先看到)、`actions` 与保存/取消同排(删除不是保存的一部分,但同样是这一页的动作)、
 * `after` 在 `<form>` 外面(那些按钮不提交表单)。标题用 `xl`,比条目页的 `2xl` 小一档,只要确认「我在改什么」。
 */
import { RouterLink } from "vue-router";
import { Button, Heading, Text } from "../ui";

withDefaults(
  defineProps<{
    /** 页头那一行。不写就不画页头。 */
    title?: string;
    /** 一句话说明这一页在做什么;不写就不显示。 */
    description?: string;
    saving?: boolean;
    submitLabel?: string;
    cancelTo: string;
    cancelLabel?: string;
  }>(),
  { title: "", description: "", saving: false, submitLabel: "保存", cancelLabel: "取消" },
);

defineEmits<{ submit: [] }>();
</script>

<template>
  <div class="flex flex-col gap-6">
    <div v-if="title || description" class="flex flex-col gap-1">
      <Heading v-if="title" :level="1" size="xl">{{ title }}</Heading>
      <Text v-if="description" size="sm" tone="muted">{{ description }}</Text>
    </div>

    <div v-if="$slots.alerts" class="flex flex-col gap-3">
      <slot name="alerts" />
    </div>

    <form class="flex flex-col gap-5" @submit.prevent="$emit('submit')">
      <slot />

      <div class="flex flex-wrap items-center gap-3 border-t border-line pt-5">
        <Button type="submit" variant="solid" tone="accent" :loading="saving">
          {{ submitLabel }}
        </Button>
        <RouterLink :to="cancelTo">
          <Button variant="ghost" type="button">{{ cancelLabel }}</Button>
        </RouterLink>
        <slot name="actions" />
      </div>
    </form>

    <slot name="after" />
  </div>
</template>
