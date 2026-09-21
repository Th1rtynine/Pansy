<script setup lang="ts">
/**
 * 一份作品的字段:新建作品时与作品编辑页共用这一段。
 * 问哪几项、每项叫什么由传进来的 `spec`(接口给的 `fields`)决定,所以同一张表既管展示也管录入,
 * 「游戏没有卷也没有数量」表现为那一段不出现。
 * 类型下拉只在新建时为真(`showType`):类型定了这一份有哪些字段,建好之后不能改。
 */
import { Input, NumberInput, FormField, Select, TagsInput, Textarea } from "../ui";

import type { EditionIn } from "../types";
import { mediaTypes } from "../mediaTypes";
import CreatorRows from "./CreatorRows.vue";

const form = defineModel<EditionIn>({ required: true });

withDefaults(
  defineProps<{
    /** 这个类型的字段名表;新建时跟着下拉走,编辑时就是这一份自己的类型。 */
    spec: Record<string, string>;
    /** 只在新建页上为真:那时类型还没定,由这里选。 */
    showType?: boolean;
  }>(),
  { showType: false },
);

const typeOptions = () => mediaTypes.value.map((item) => ({ value: item.value, label: item.label }));
</script>

<template>
  <div class="flex flex-col gap-4">
    <FormField v-if="showType" label="类型" description="必填,建好之后不能改" required>
      <Select v-model="form.media_type" :options="typeOptions()" />
    </FormField>

    <!--
      标题这一格留了一个动作位:编辑页把「按名字找」摆在它旁边,名字填完就能直接点;新建页那一侧不传,
      因为那边的名字在上一层(作品总标题)。
    -->
    <FormField label="标题" description="与作品总标题不同时才填">
      <div class="flex flex-wrap items-center gap-2">
        <Input v-model="form.title" class="min-w-0 flex-1" />
        <slot name="title-action" />
      </div>
    </FormField>

    <FormField
      v-if="spec.time"
      :label="spec.time"
      description="例如 2015、2015-04 或 2015-04-01,留空表示未知"
    >
      <Input v-model="form.published_on" />
    </FormField>

    <FormField label="简介">
      <Textarea v-model="form.summary" :rows="4" />
    </FormField>

    <FormField v-if="spec.org" :label="spec.org">
      <Input v-model="form.org" />
    </FormField>

    <FormField v-if="spec.status" :label="spec.status" :description="spec.status_hint">
      <Input v-model="form.release_status" />
    </FormField>

    <FormField v-if="spec.count" :label="spec.count">
      <NumberInput v-model="form.volume_count" :min="0" />
    </FormField>

    <FormField label="作者与角色" description="一行一位;名字打错了去作者那一页改">
      <CreatorRows v-model="form.creators" />
    </FormField>

    <FormField label="标签" description="输入后回车;同一个词在不同类型下是两条">
      <TagsInput v-model="form.tags" />
    </FormField>
  </div>
</template>
