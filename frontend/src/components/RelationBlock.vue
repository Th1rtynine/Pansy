<script setup lang="ts">
/**
 * 关联作品那一段,跟着页面所在的那一层显示:作品页上列被关联的作品,作品总标题页上列被关联的
 * 作品总标题 —— 点一条关联落到的总是与当前页同一层的页,不会掉进某一份单独的作品里。
 * 标题就是一条关联说过的全部,没有种类可印:「关联作品」是页面上的词,不是库里的取值。
 */
import { Heading, Text } from "../ui";

import type { EditionRef, LinkedWorkOut } from "../types";
import CarrierRow from "./CarrierRow.vue";
import WorkRow from "./WorkRow.vue";

defineProps<{
  /** 作品层:被关联的作品。 */
  editions?: EditionRef[];
  /** 作品总标题层:被关联的作品总标题,以及各有多少份作品连着。 */
  works?: LinkedWorkOut[];
}>();
</script>

<template>
  <section class="flex flex-col gap-2">
    <Heading :level="2" size="lg">关联作品</Heading>

    <ul v-if="works?.length" class="flex flex-col divide-y divide-line">
      <li v-for="other in works" :key="other.id">
        <RouterLink
          :to="`/works/${other.id}`"
          class="flex flex-col gap-1 rounded-control px-3 py-3 transition-colors hover:bg-state-hover focus-visible:bg-state-hover active:bg-state-press"
        >
          <Text size="lg" weight="medium">{{ other.title }}</Text>
          <Text size="sm" tone="muted">
            {{ other.published_on ? `${other.published_on} · ` : ""
            }}{{ other.edition_count }} 个作品与之关联
          </Text>
        </RouterLink>
      </li>
    </ul>

    <ul v-else-if="editions?.length" class="flex flex-col divide-y divide-line">
      <CarrierRow v-for="other in editions" :key="other.id" :edition="other" />
    </ul>

    <Text v-else size="sm" tone="muted">暂无关联作品。</Text>
  </section>
</template>
