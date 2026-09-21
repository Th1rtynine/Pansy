<script setup lang="ts">
/**
 * 「真的要删?」—— 行内确认,不是浮层:点触发器后原地换成一句问话加两颗按钮,代价是这行会变高一点,
 * 换来不写浮层代码、键盘与读屏软件天然就对、手机上不会点歪。
 * 默认插槽放触发器,`on-confirm` 放真要做的事,`tone` 分 accent / danger。
 */
import { ref } from "vue";
import Button from "./Button.vue";

const props = withDefaults(
  defineProps<{
    title: string;
    description?: string;
    confirmText?: string;
    cancelText?: string;
    tone?: "accent" | "danger";
    onConfirm?: () => unknown;
  }>(),
  { confirmText: "确定", cancelText: "取消", tone: "accent" },
);

const emit = defineEmits<{ cancel: [] }>();
const open = ref(false);
const busy = ref(false);

async function confirm() {
  if (!props.onConfirm) return;
  busy.value = true;
  try {
    await props.onConfirm();
    open.value = false;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <span v-if="!open" class="inline-flex" @click="open = true">
    <slot />
  </span>

  <span v-else class="inline-flex flex-wrap items-center gap-2 rounded-control bg-subtle px-2 py-1">
    <span class="text-sm text-fg">
      {{ title }}
      <span v-if="description" class="text-xs text-muted">{{ description }}</span>
    </span>
    <Button size="sm" variant="solid" :tone="tone" :loading="busy" @click="confirm">
      {{ confirmText }}
    </Button>
    <Button
      size="sm"
      variant="ghost"
      @click="
        open = false;
        emit('cancel');
      "
    >
      {{ cancelText }}
    </Button>
  </span>
</template>
