<script setup lang="ts">
/**
 * 右下角那个「回到顶部」:滚过 40px 就出现,位置飘在正文右边那条空白里(`bottom-28` = 112px,
 * 往右到正文右边缘再往外 5rem,窗口比正文窄时退回离边 1rem)。
 * 右边距用 `100%` 而不是 `100vw`:后者含滚动条,而正文列按不含滚动条的布局宽居中,混用会让按钮横移半个滚动条。
 * 形状是方角圆框 + 圆头箭头,`bg-surface/80` 加背景模糊,不用阴影。滚动走 `smooth`,开了减少动效就直接跳过去。
 */
import { onMounted, onUnmounted, ref } from "vue";

const shown = ref(false);

function onScroll() {
  shown.value = window.scrollY > 40;
}

function toTop() {
  const quiet = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  window.scrollTo({ top: 0, behavior: quiet ? "auto" : "smooth" });
}

onMounted(() => {
  onScroll(); // 刷新时可能就停在半路,所以先看一眼
  window.addEventListener("scroll", onScroll, { passive: true });
});

onUnmounted(() => window.removeEventListener("scroll", onScroll));
</script>

<template>
  <Transition
    enter-from-class="opacity-0"
    enter-active-class="transition-opacity"
    leave-to-class="opacity-0"
    leave-active-class="transition-opacity"
  >
    <button
      v-if="shown"
      type="button"
      aria-label="回到顶部"
      title="回到顶部"
      :class="[
        'fixed bottom-28 z-(--pn-z-overlay) flex size-10 items-center justify-center',
        'right-[max(1rem,calc((100%-var(--pn-shell-width))/2-5rem))]',
        'rounded-control border border-line bg-surface/80 text-muted backdrop-blur-sm',
        'transition-colors hover:bg-surface hover:text-fg active:bg-state-press',
      ]"
      @click="toTop"
    >
      <!-- 圆头的向上箭头:两端与转折都收圆,不是 `↑` 那种尖角 -->
      <svg
        viewBox="0 0 24 24"
        class="size-5"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
        stroke-linecap="round"
        stroke-linejoin="round"
        aria-hidden="true"
      >
        <path d="M6 14.5 12 8.5l6 6" />
      </svg>
    </button>
  </Transition>
</template>
