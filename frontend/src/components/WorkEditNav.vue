<script setup lang="ts">
/**
 * 作品编辑页的两层目录:上面一档是作品总标题(单独一行,小字写「作品总标题」),一条细线分开,下面是各份作品;
 * 两层不能长得一样还一起编号,否则加两份漫画会读成「2 漫画、3 漫画」,像在数第几份。新建页的项目在当前表单内
 * 切换,已有作品的项目链接到各自的编辑地址。`aside` 上的 `min-w-0` 必须有:调用处都在 `lg:grid-cols-[15rem_minmax(0,1fr)]`
 * 里,而 `lg` 以下是一列宽度 `auto` 的轨道、由内容的最小宽度决定 —— 不加,整个页面就横着滚。
 */
import { computed } from "vue";
import { RouterLink } from "vue-router";

type WorkEditNavItem = {
  key: string;
  label: string;
  detail: string;
  done?: boolean;
  to?: string;
};

const props = withDefaults(
  defineProps<{
    items: WorkEditNavItem[];
    active: string;
    canAdd?: boolean;
    addTo?: string;
  }>(),
  { canAdd: true, addTo: "" },
);

const emit = defineEmits<{ select: [key: string]; add: [] }>();

/** 上面那一档:第一项就是总标题(调用处都把作品信息排在第一个)。 */
const head = computed(() => props.items[0] ?? null);
/** 下面那一档:一份份作品,同级的一串。 */
const tail = computed(() => props.items.slice(1));

function itemClass(active: boolean): string[] {
  return [
    "flex min-w-44 items-center gap-3 rounded-control border px-3 py-2 text-left transition-colors lg:min-w-0",
    active
      ? "border-accent bg-accent-soft text-accent-text"
      : "border-transparent text-fg hover:bg-state-hover active:bg-state-press",
  ];
}

/** 总标题那一行:比下面的条目更"轻"一点(它是所属,不是其中一份)。 */
function headClass(active: boolean): string[] {
  return [
    "flex min-w-44 items-center gap-3 rounded-control border px-3 py-2 text-left transition-colors lg:min-w-0",
    active
      ? "border-accent bg-accent-soft text-accent-text"
      : "border-transparent text-fg hover:bg-state-hover active:bg-state-press",
  ];
}

const addClass =
  "flex min-w-44 items-center gap-2 rounded-control border border-dashed border-line px-3 py-2 text-left text-muted transition-colors hover:border-accent hover:bg-state-hover hover:text-accent-text lg:min-w-0";
</script>

<template>
  <aside class="min-w-0 lg:sticky lg:top-24">
    <nav
      class="flex gap-2 overflow-x-auto rounded-card border border-line bg-surface p-2 [scrollbar-width:none] lg:flex-col lg:overflow-visible [&::-webkit-scrollbar]:hidden"
      aria-label="作品编辑层级"
    >
      <!-- 上面一档:作品总标题。**不编号、不参与下面那一串。** -->
      <RouterLink
        v-if="head && head.to && active !== head.key"
        :to="head.to"
        :class="headClass(false)"
      >
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="text-sm text-muted">作品总标题</span>
          <span class="truncate font-medium">{{ head.detail || head.label }}</span>
        </span>
        <span class="text-muted" aria-hidden="true">›</span>
      </RouterLink>
      <button
        v-else-if="head"
        type="button"
        :aria-current="active === head.key ? 'step' : undefined"
        :class="headClass(active === head.key)"
        @click="emit('select', head.key)"
      >
        <span class="flex min-w-0 flex-1 flex-col">
          <span class="text-sm text-muted">作品总标题</span>
          <span class="truncate font-medium">{{ head.detail || head.label }}</span>
        </span>
        <span v-if="head.done" class="text-accent-text" aria-label="已填写">✓</span>
      </button>

      <div v-if="tail.length" class="hidden items-center gap-2 px-3 pt-1 lg:flex">
        <span class="text-sm font-medium text-muted">作品</span>
        <span class="h-px flex-1 bg-line"></span>
      </div>

      <!-- 下面一档:一份份作品,同级的一串,**不编号**。 -->
      <template v-for="item in tail" :key="item.key">
        <RouterLink
          v-if="item.to && active !== item.key"
          :to="item.to"
          :class="itemClass(active === item.key)"
        >
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="font-medium">{{ item.label }}</span>
            <span class="truncate text-sm text-muted">{{ item.detail }}</span>
          </span>
          <span class="text-muted" aria-hidden="true">›</span>
        </RouterLink>

        <button
          v-else
          type="button"
          :aria-current="active === item.key ? 'step' : undefined"
          :class="itemClass(active === item.key)"
          @click="emit('select', item.key)"
        >
          <span class="flex min-w-0 flex-1 flex-col">
            <span class="font-medium">{{ item.label }}</span>
            <span class="truncate text-sm text-muted">{{ item.detail }}</span>
          </span>
          <span v-if="item.done" class="text-accent-text" aria-label="已填写">✓</span>
        </button>
      </template>

      <RouterLink v-if="canAdd && addTo" :to="addTo" :class="addClass">
        <span class="flex size-7 items-center justify-center text-lg" aria-hidden="true">＋</span>
        <span class="font-medium">添加作品</span>
      </RouterLink>
      <button
        v-else-if="canAdd"
        type="button"
        :class="addClass"
        @click="emit('add')"
      >
        <span class="flex size-7 items-center justify-center text-lg" aria-hidden="true">＋</span>
        <span class="font-medium">添加作品</span>
      </button>

      <slot name="after-add" />
    </nav>
  </aside>
</template>
