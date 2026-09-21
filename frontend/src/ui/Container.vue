<script setup lang="ts">
/**
 * 一行内容的最宽度。
 *
 * **为什么要有最大宽度**:一行字太长,眼睛回行时会找错行。所以正文区域有个上限,
 * 窗口再宽也不会拉成一条长线。
 */
withDefaults(defineProps<{ size?: "sm" | "md" | "lg" | "xl" | "shell" | "header" }>(), {
  size: "shell",
});

const SIZES = {
  sm: "max-w-xl",
  md: "max-w-3xl",
  lg: "max-w-5xl",
  xl: "max-w-7xl",
  /** 壳子:全站那一列的宽度。它读 `--pn-shell-width`(值在 semantic.css,理由也在那儿),
   *  因为右下角那个「回到顶部」要贴在同一个右边上 —— 两处读同一个数,改宽度才只改一处。 */
  shell: "max-w-(--pn-shell-width)",
  /** 顶栏比正文宽,让站名、导航与会展开的搜索框能稳定地留在同一张长卡片里。 */
  header: "max-w-(--pn-header-width)",
};
</script>

<template>
  <div :class="['mx-auto w-full px-4', SIZES[size]]">
    <slot />
  </div>
</template>
