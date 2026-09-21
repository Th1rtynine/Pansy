<script setup lang="ts">
/**
 * 手机上那一条**底部导航**,宽屏上不存在(整个组件 `md:hidden`)。**两条导航、一个断点**,不是把顶栏那条挪下来 ——
 * 两份同时留在 DOM 里,谁露面由 CSS 决定(要靠同一份数据保持一致)。**排布围着「主页」折过来**:接口回来的那一排
 * 从中间折一下,主页居中,两边各两个,所以顶栏与这一条的左右顺序正好相反。**每一格都带 2px 透明边框** —— 不这样的话
 * 亮起来的那一格会比别的高出 4px、整条抖一下(高度 59px 不变,`<main>` 留了等高的底部留白);底下留 `env(safe-area-inset-bottom)`。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";

import HomeIcon from "./HomeIcon.vue";
import MediaTypeIcon from "./MediaTypeIcon.vue";

const props = defineProps<{
  /** 四个类型,顺序就是接口回来的那个顺序(漫画、轻小说、Gal、动画)。 */
  items: { value: string; label: string }[];
  /** 当前在哪一类上(不在列表页时为 null,那时谁也不亮)。 */
  current: string | null;
  /** 是不是「全部」那一页 —— 主页那一格亮不亮。 */
  onHome: boolean;
}>();

/** 换一类由外壳去改地址;这里只报「点了哪一个」。 */
const emit = defineEmits<{ pick: [value: string] }>();

/** 围着中间折:后一半倒过来放左边,前一半倒过来放右边,主页落在正中间。 */
const half = computed(() => Math.ceil(props.items.length / 2));
const left = computed(() => props.items.slice(half.value).reverse());
const right = computed(() => props.items.slice(0, half.value).reverse());

/** 每一格长一个样,只是亮不亮不同。 */
function slotClass(active: boolean) {
  return [
    "flex flex-1 flex-col items-center gap-0.5 rounded-control border-2 px-1 pt-2 pb-1.5 text-xs transition-colors",
    active
      ? "border-mark font-medium text-mark-text"
      : "border-transparent text-muted active:bg-state-press",
  ];
}
</script>

<template>
  <nav
    class="fixed inset-x-0 bottom-0 z-(--pn-z-overlay) border-t border-line bg-surface/85 pb-[env(safe-area-inset-bottom)] backdrop-blur-md md:hidden"
    aria-label="类型"
  >
    <div class="flex items-stretch">
      <button
        v-for="item in left"
        :key="item.value"
        type="button"
        :aria-current="current === item.value ? 'page' : undefined"
        :class="slotClass(current === item.value)"
        @click="emit('pick', item.value)"
      >
        <MediaTypeIcon :value="item.value" size="size-5" />
        {{ item.label }}
      </button>

      <!-- 中间那一枚:回到「全部」,地址是固定的,所以是一条直链接而不是按钮 -->
      <RouterLink
        to="/works"
        :aria-current="onHome ? 'page' : undefined"
        :class="slotClass(onHome)"
      >
        <HomeIcon size="size-5" />
        主页
      </RouterLink>

      <button
        v-for="item in right"
        :key="item.value"
        type="button"
        :aria-current="current === item.value ? 'page' : undefined"
        :class="slotClass(current === item.value)"
        @click="emit('pick', item.value)"
      >
        <MediaTypeIcon :value="item.value" size="size-5" />
        {{ item.label }}
      </button>
    </div>
  </nav>
</template>
