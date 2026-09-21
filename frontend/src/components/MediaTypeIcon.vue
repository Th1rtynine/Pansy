<script setup lang="ts">
/**
 * 四个媒体类型各一枚线性小图标,给顶栏那一条用:图像框(漫画)、书(轻小说)、对话气泡(游戏 ——
 * 这个库里的游戏以 galgame 为主,galgame 的样子就是一块对话框,比手柄贴切)、圆里一个播放三角(动画)。
 * 四枚都走 `currentColor`,`color` 跟着用的地方走;做成内联路径而不是引图标库,因为全站只有这一处要图标。
 * 尺寸由调用方给:顶栏那一条 16px,手机上那条底部导航 20px(`size` 收一个类名)。
 */
withDefaults(defineProps<{ value: string; size?: string }>(), { size: "size-4" });
</script>

<template>
  <!-- 漫画:一格画面 -->
  <svg
    v-if="value === 'manga'"
    viewBox="0 0 24 24"
    :class="['shrink-0', size]"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <rect x="3.5" y="4.5" width="17" height="15" rx="2" />
    <path d="M3.5 15.5 8 11l5 5 3-3 4.5 4.5" />
    <circle cx="9" cy="9" r="1.2" fill="currentColor" stroke="none" />
  </svg>

  <!-- 轻小说:一本合着的书 -->
  <svg
    v-else-if="value === 'light_novel'"
    viewBox="0 0 24 24"
    :class="['shrink-0', size]"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path d="M7 4h9.5A2.5 2.5 0 0 1 19 6.5v13a.5.5 0 0 1-.5.5H7a2.5 2.5 0 0 1-2.5-2.5v-11A2.5 2.5 0 0 1 7 4Z" />
    <path d="M9.5 4v16" />
  </svg>

  <!-- 游戏(这个库里以 galgame 为主):一块对话气泡 -->
  <svg
    v-else-if="value === 'game'"
    viewBox="0 0 24 24"
    :class="['shrink-0', size]"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <path
      d="M20.5 11.8c0 3.9-3.8 7.1-8.5 7.1-1 0-2-.1-2.9-.4l-4.6 1.6 1.2-3.4a6.8 6.8 0 0 1-2.2-4.9c0-3.9 3.8-7.1 8.5-7.1s8.5 3.2 8.5 7.1Z"
    />
  </svg>

  <!-- 动画:圆里一个播放三角 -->
  <svg
    v-else
    viewBox="0 0 24 24"
    :class="['shrink-0', size]"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <circle cx="12" cy="12" r="8.2" />
    <path d="M10.3 9.1 15 12l-4.7 2.9Z" fill="currentColor" stroke="none" />
  </svg>
</template>
