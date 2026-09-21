<script setup lang="ts">
/**
 * 一张卷的卡片:封面 + 序号 + 名字,点整张卡进那一卷的页。照 `CarrierCard.vue` 写:一卷信息少(序号、
 * 名字、简介),铺成长条会显得空,卡片才一眼看完,而「收了几卷」本来就是一个封面网格回答得最好的问题。
 * 名字那行有序号就写「第 4 卷」、没有序号才退回名字、两样都没有才写那个量词本身 —— 一整套漫画里
 * 「第 4 卷」比「(没有名字)」有用得多。没有封面时 `Cover.vue` 画占位(名字的头两个字),序号与名字不依赖图。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";
import { Cover, Text } from "../ui";

import type { VolumeOut } from "../types";

const props = withDefaults(defineProps<{ volume: VolumeOut; unit?: string }>(), { unit: "" });

const label = computed(() => {
  const unit = props.unit || "卷";
  if (props.volume.volume_number === null) return props.volume.title || unit;
  return `第 ${props.volume.volume_number} ${unit}`;
});
</script>

<template>
  <RouterLink
    :to="`/volumes/${volume.id}`"
    class="flex flex-col gap-2 rounded-card border border-line p-2.5 transition-colors hover:bg-state-hover focus-visible:bg-state-hover active:bg-state-press"
  >
    <Cover
      :title="volume.title || label"
      :src="volume.cover_url"
      :width="volume.cover_width"
      :height="volume.cover_height"
      size="card"
    />

    <span class="flex flex-col gap-0.5">
      <Text size="sm" weight="medium">{{ label }}</Text>
      <!-- 有名字才多占一行;一整套漫画里绝大多数卷没有自己的名字,那时卡片更矮 -->
      <!--
        真实名字**不在这里印**:一部漫画的每一卷在源上都叫「系列名 (01)」,印在卡片上只是
        把「第 1 卷」又说一遍;点进去那一页才是看它的地方。
      -->
    </span>
  </RouterLink>
</template>
