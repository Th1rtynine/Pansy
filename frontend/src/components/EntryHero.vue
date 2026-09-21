<script setup lang="ts">
/**
 * 条目页的第一屏:左边一张图,右边自上而下是状态、标题、原名、一行元数据、一排动作(四个插槽,
 * 只放调用方有的那些 —— 作品页有原名,载体页没有,作者页用原名那行放别名)。
 * 左边由 `shape` 决定:作品是 3:4 书封面,人是圆头像;窄屏上小一圈但仍留在左边,不改成上下堆叠。
 */
import { Avatar, Cover, Heading, Text } from "../ui";

withDefaults(
  defineProps<{
    /** 左边那个占位里显示什么名字:封面取头两个字,头像取头一个字。 */
    lead: string;
    title: string;
    /** 官方名字(原名)。有就小字跟在标题后面。 */
    original?: string | null;
    /** 左边是书封面还是人像。 */
    shape?: "cover" | "avatar";
    /** 封面地址(`/covers/...`);没有就画占位。 */
    src?: string | null;
    /** 原图的像素尺寸,让封面按真实比例占位(见 ui/Cover.vue)。 */
    width?: number | null;
    height?: number | null;
  }>(),
  { original: null, shape: "cover", src: null, width: null, height: null },
);
</script>

<template>
  <div class="flex items-start gap-4 border-b border-line pb-5 sm:gap-6">
    <!-- 第一屏这张图**不懒加载**:它就在眼前,懒了只是让它更晚到。点开看大图也在这里开 -->
    <Cover
      v-if="shape === 'cover'"
      :title="lead"
      :src="src"
      :width="width"
      :height="height"
      size="hero"
      :lazy="false"
      enlarge
    />
    <Avatar v-else :name="lead" :src="src" size="hero" />

    <div class="flex min-w-0 flex-1 flex-col gap-2">
      <div v-if="$slots.chips" class="flex flex-wrap items-center gap-2">
        <slot name="chips" />
      </div>

      <Heading :level="1" size="2xl">
        {{ title }}
        <Text v-if="original" size="base" tone="faint">{{ original }}</Text>
      </Heading>

      <div v-if="$slots.under" class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <slot name="under" />
      </div>

      <div v-if="$slots.meta" class="flex flex-wrap items-center gap-x-3 gap-y-1">
        <slot name="meta" />
      </div>

      <div v-if="$slots.actions" class="flex flex-wrap items-center gap-2 pt-1">
        <slot name="actions" />
      </div>
    </div>
  </div>
</template>
