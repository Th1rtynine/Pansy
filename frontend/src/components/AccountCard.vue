<script setup lang="ts">
/**
 * 一张账号卡:头像 + 名字 + 一行附注 + 一句签名。**设置页三个源都用它**
 * (Hikarinagi 登录着谁、Bangumi 与 VNDB 那个令牌对应谁),所以形状放在这里只写一遍。
 *
 * 它只负责「画出一个账号」,不管按钮 —— 登录、退出、验证各是各的动作,由调用方摆在自己那边。
 */
import { computed } from "vue";
import { Avatar, Text } from "../ui";

const props = withDefaults(
  defineProps<{
    /** 显示用的名字,调用方已经挑好(昵称优先)。 */
    name: string;
    /** 显示名的来源,用来在名字为空时给头像占位一个字。 */
    source?: string;
    /** 附注那一行,比如 `@叁拾玖 · ID 1182021`。空着就不显示。 */
    note?: string;
    avatarUrl?: string;
    signature?: string;
    /** 账号当前状态,放在身份信息下方,例如「已登录」或「已连接」。 */
    status?: string;
  }>(),
  { source: "", note: "", avatarUrl: "", signature: "", status: "" },
);

const shown = computed(() => props.name || props.source || "?");
</script>

<template>
  <div class="flex items-center gap-4">
    <Avatar :name="shown" :src="avatarUrl || null" size="hero" />
    <div class="flex min-w-0 flex-col gap-0.5">
      <Text size="base" weight="medium" class="truncate">{{ shown }}</Text>
      <Text v-if="note" size="sm" tone="muted" class="truncate">{{ note }}</Text>
      <Text v-if="signature" size="sm" tone="faint" class="truncate">{{ signature }}</Text>
      <span v-if="status" class="mt-1 inline-flex items-center gap-1.5 text-sm text-success-text">
        <span class="size-1.5 rounded-full bg-success" aria-hidden="true"></span>
        {{ status }}
      </span>
    </div>
  </div>
</template>
