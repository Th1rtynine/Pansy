<script setup lang="ts">
/**
 * 「作者与角色」那几行:名字一个框,角色一个框,可以加减。
 *
 * 接口那一层收的是 `[{name, role}]`,所以**这里不必再拆文本** —— 拆的规则只有一份,在
 * 后端。一行一行摆着,加一位就是加一行,也比让人在一行里写「名字 角色」更好用。
 */
import { Button, Input, Text } from "../ui";

import type { CreatorLinkIn } from "../types";

const rows = defineModel<CreatorLinkIn[]>({ required: true });

function add() {
  rows.value = [...rows.value, { name: "", role: "" }];
}

function drop(index: number) {
  rows.value = rows.value.filter((_, position) => position !== index);
}

function update(index: number, key: "name" | "role", value: string) {
  rows.value = rows.value.map((row, position) =>
    position === index ? { ...row, [key]: value } : row,
  );
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <div v-for="(row, index) in rows" :key="index" class="flex flex-wrap items-center gap-2">
      <Input
        :model-value="row.name"
        placeholder="名字"
        class="w-48"
        @update:model-value="(value) => update(index, 'name', value)"
      />
      <Input
        :model-value="row.role"
        placeholder="角色,例如 原作"
        class="w-40"
        @update:model-value="(value) => update(index, 'role', value)"
      />
      <Button variant="ghost" tone="danger" size="sm" @click="drop(index)">移除</Button>
    </div>

    <div class="flex items-center gap-3">
      <Button variant="outline" size="sm" @click="add">+ 加一位</Button>
      <Text v-if="!rows.length" size="sm" tone="faint">
        留空就是不记作者。
      </Text>
    </div>
  </div>
</template>
