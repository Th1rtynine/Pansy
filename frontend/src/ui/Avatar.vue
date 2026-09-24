<script setup lang="ts">
/**
 * 头像位:管位置与尺寸,不碰图片本身 —— 没有 `src` 就画占位,版式不变,`size` 分 row / hero。
 * 圆形是为了跟 3:4 的封面位(Cover.vue)一眼分得开,列表里两种东西不会看混。
 * 占位是姓名头一个字,底色走 `bg-subtle` 不掺主色:一屏十几行淡紫方块,「少量颜色点缀」就没了。
 *
 * **取不到的图当成没有图**,与 `Cover.vue` 同一条规矩:地址是从外部站点原样搬来的,对方换了路径、
 * 或者那份缓存里的地址本来就写坏了,浏览器就会画一个破图标(甚至一片空白)—— 而占位明明就在手边。
 */
import { computed, ref, watch } from "vue";

const props = withDefaults(defineProps<{ name: string; src?: string | null; size?: "row" | "hero" }>(), {
  src: null,
  size: "row",
});

const SIZES = { row: "size-11 text-base", hero: "size-20 text-2xl sm:size-24" };

const failed = ref(false);
// 换了一个地址(**包括从「没有图」换成「有图」**)就重新试一次:失败状态只属于那一个地址。
watch(
  () => props.src,
  () => (failed.value = false),
);

/** 图取不到就当没有图:走占位,而不是让浏览器画一个破图标。 */
const shown = computed(() => (props.src && !failed.value ? props.src : null));

function initial(name: string) {
  return name.replace(/\s+/g, "").slice(0, 1);
}
</script>

<template>
  <div
    :class="[
      SIZES[size],
      'flex shrink-0 items-center justify-center overflow-hidden rounded-full border border-line bg-subtle',
    ]"
  >
    <img v-if="shown" :src="shown" :alt="name" class="size-full object-cover" @error="failed = true" />
    <!-- 占位对读屏软件没有意义:名字就在旁边 -->
    <span v-else class="text-faint" aria-hidden="true">{{ initial(name) }}</span>
  </div>
</template>
