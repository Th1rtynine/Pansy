<script setup lang="ts">
/**
 * 头像位:管位置与尺寸,不碰图片本身 —— 没有 `src` 就画占位,版式不变,`size` 分 row / hero。
 * 圆形是为了跟 3:4 的封面位(Cover.vue)一眼分得开,列表里两种东西不会看混。
 * 占位是姓名头一个字,底色走 `bg-subtle` 不掺主色:一屏十几行淡紫方块,「少量颜色点缀」就没了。
 */
withDefaults(defineProps<{ name: string; src?: string | null; size?: "row" | "hero" }>(), {
  src: null,
  size: "row",
});

const SIZES = { row: "size-11 text-base", hero: "size-20 text-2xl sm:size-24" };

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
    <img v-if="src" :src="src" :alt="name" class="size-full object-cover" />
    <!-- 占位对读屏软件没有意义:名字就在旁边 -->
    <span v-else class="text-faint" aria-hidden="true">{{ initial(name) }}</span>
  </div>
</template>
