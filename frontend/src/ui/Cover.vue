<script setup lang="ts">
/**
 * 封面位:一张图、一个形状、一个「点开看大图」。默认 3:4,`hero` 按接口给的 `width` / `height` 走真实比例;
 * 列表与卡片固定 3:4 裁切。一屏几十张离得近才取(首屏传 `lazy: false`),取不到退回标题头两个字的占位。
 */
import { computed, ref } from "vue";
import Button from "./Button.vue";

const props = withDefaults(
  defineProps<{
    title: string;
    src?: string | null;
    /** 原图的像素尺寸,来自接口(`cover_width` / `cover_height`);少一个就不用。 */
    width?: number | null;
    height?: number | null;
    /** row 用在列表行里,hero 用在条目页第一屏,card 用在卡片里(占满卡片宽度)。 */
    size?: "row" | "hero" | "card";
    /** 首屏那张传 false。 */
    lazy?: boolean;
    /** 点开看大图。开之前先想清楚:它会把封面变成一个按钮。 */
    enlarge?: boolean;
  }>(),
  { src: null, width: null, height: null, size: "row", lazy: true, enlarge: false },
);

const SIZES = {
  row: "w-11 text-sm",
  hero: "w-28 text-2xl sm:w-40",
  card: "w-full text-xl",
};

const failed = ref(false);

/** 图取不到就当没有图:走占位,而不是让浏览器画一个破图标。 */
const shown = computed(() => (props.src && !failed.value ? props.src : null));
const zoomable = computed(() => props.enlarge && shown.value !== null);

const ratio = computed(() => {
  if (props.size !== "hero" || !props.width || !props.height) return null;
  return `${props.width} / ${props.height}`;
});

/** 头两个字。日文原名、书名号、空格都先去掉,免得占位里出现一个「》」。 */
function initials(title: string) {
  return title.replace(/[\s《》「」『』()（）]/g, "").slice(0, 2);
}

const box = ref<HTMLDialogElement | null>(null);
</script>

<template>
  <div
    :class="[
      SIZES[size],
      'aspect-[3/4] shrink-0 overflow-hidden rounded-control border border-line bg-subtle',
    ]"
    :style="ratio ? { aspectRatio: ratio } : undefined"
  >
    <button
      v-if="zoomable"
      type="button"
      class="block size-full cursor-zoom-in"
      :aria-label="`看大图:${title}`"
      @click="box?.showModal()"
    >
      <img
        :src="shown ?? undefined"
        :alt="title"
        :loading="lazy ? 'lazy' : 'eager'"
        decoding="async"
        class="size-full object-cover"
        @error="failed = true"
      />
    </button>

    <img
      v-else-if="shown"
      :src="shown"
      :alt="title"
      :loading="lazy ? 'lazy' : 'eager'"
      decoding="async"
      class="size-full object-cover"
      @error="failed = true"
    />

    <!-- 占位对读屏软件没有意义:标题就在旁边,所以藏起来 -->
    <div v-else class="flex size-full items-center justify-center text-faint" aria-hidden="true">
      {{ initials(title) }}
    </div>

    <!--
      大图。点哪儿都关:图片、按钮、边上那圈暗色都算。进场淡入用 `@starting-style`,因为 `<dialog>` 在
      `showModal()` 之前是 `display:none`,没有「上一帧」可以过渡;退场不做过渡,按 Esc 立刻消失更利落。
    -->
    <dialog
      v-if="enlarge"
      ref="box"
      class="m-auto max-w-none bg-transparent p-0 transition-opacity duration-(--pn-duration-base) starting:opacity-0 [&::backdrop]:bg-scrim"
      :aria-label="`${title} 的封面`"
      @click="box?.close()"
    >
      <div class="flex flex-col items-center gap-3">
        <img
          v-if="shown"
          :src="shown"
          :alt="title"
          class="max-h-[85vh] max-w-[90vw] rounded-control object-contain"
        />
        <Button variant="outline" tone="neutral" size="sm" @click="box?.close()">关闭</Button>
      </div>
    </dialog>
  </div>
</template>
