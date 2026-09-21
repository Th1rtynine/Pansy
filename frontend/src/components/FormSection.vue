<script setup lang="ts">
/**
 * 表单里的一段:一个小标题 + 一句说明 + 这一段的字段;分段是因为一张表单多则十几项(作品页就有
 * 时间、出版方、状态、卷数、简介、作者、标签、卷),不分段就是一片输入框,标题本身就是「你在填什么」。
 * 段与段之间是一条 1px 细线(`border-t border-line`),不用卡片与阴影,与条目页的分段一致;每一段都有上线,第一段也不例外。
 * 说明只写「这一项填什么」,不写「必填」—— 必填由 `FormField` 的 `required` 负责。
 */
import { Heading, Text } from "../ui";

withDefaults(defineProps<{ title: string; description?: string }>(), { description: "" });
</script>

<template>
  <section class="flex flex-col gap-3 border-t border-line pt-5">
    <Heading :level="2" size="lg">{{ title }}</Heading>
    <Text v-if="description" size="sm" tone="muted">{{ description }}</Text>
    <slot />
  </section>
</template>
