<script setup lang="ts">
/**
 * 一份作品的字段:新建作品时与作品编辑页共用这一段。
 * 问哪几项、每项叫什么由传进来的 `spec`(接口给的 `fields`)决定,所以同一张表既管展示也管录入,
 * 「游戏没有卷也没有数量」表现为那一段不出现。
 * 类型下拉只在新建时为真(`showType`):类型定了这一份有哪些字段,建好之后不能改。
 */
import { Button, Input, NumberInput, FormField, Select, TagsInput, Textarea } from "../ui";

import type { EditionIn } from "../types";
import { mediaTypes } from "../mediaTypes";
import { archiveFieldsOf, hasPlatforms } from "../archiveFields";
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

    <details class="rounded-panel border border-line bg-surface-soft p-4">
      <summary class="cursor-pointer text-sm text-muted">更多档案</summary>
      <div class="mt-4 grid gap-4 sm:grid-cols-2">
        <FormField v-for="field in archiveFieldsOf(form.media_type)" :key="field.key" :label="field.label">
          <Input v-model="form[field.key]" :placeholder="field.placeholder" />
        </FormField>
      </div>
      <div class="mt-4 flex flex-col gap-4">
        <FormField v-if="hasPlatforms(form.media_type)" label="运行 / 播放平台"><TagsInput v-model="form.platforms" /></FormField>
        <FormField label="参与机构" description="保留机构在这一版本中的职责">
          <div class="flex flex-col gap-2">
            <div v-for="(item, index) in form.organizations" :key="index" class="grid grid-cols-[1fr_8rem_auto] gap-2">
              <Input v-model="item.name" placeholder="机构" /><Input v-model="item.role" placeholder="职责" />
              <Button variant="ghost" size="sm" type="button" @click="form.organizations.splice(index, 1)">×</Button>
            </div>
            <Button variant="soft" size="sm" type="button" class="self-start" @click="form.organizations.push({ name: '', role: '' })">＋ 添加机构</Button>
          </div>
        </FormField>
        <FormField label="官方入口">
          <div class="flex flex-col gap-2">
            <div v-for="(item, index) in form.official_links" :key="index" class="grid grid-cols-[8rem_1fr_auto] gap-2">
              <Input v-model="item.label" placeholder="名称" /><Input v-model="item.url" placeholder="https://" />
              <Button variant="ghost" size="sm" type="button" @click="form.official_links.splice(index, 1)">×</Button>
            </div>
            <Button variant="soft" size="sm" type="button" class="self-start" @click="form.official_links.push({ label: '', url: '' })">＋ 添加入口</Button>
          </div>
        </FormField>
      </div>
    </details>

    <FormField label="本地资源" description="程序、文件或文件夹的本机路径；当前先保存位置，不会自动执行">
      <Input
        v-model="form.local_path"
        placeholder="例如 D:\\Library\\作品名 或游戏程序路径"
        class="font-mono"
      />
    </FormField>

    <FormField label="作者与角色" description="一行一位;名字打错了去作者那一页改">
      <CreatorRows v-model="form.creators" />
    </FormField>

    <FormField label="标签" description="输入后回车;同一个词在不同类型下是两条">
      <TagsInput v-model="form.tags" />
    </FormField>
  </div>
</template>
