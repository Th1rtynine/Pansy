<script setup lang="ts">
/** 地址对不上任何一页时的那一页。与后端的错误页说同样的话。 */
import { RouterLink } from "vue-router";
import { Button, Empty } from "../ui";
</script>

<template>
  <Empty title="这一页不存在" description="地址可能写错了,或者这条记录已经不在了。">
    <template #actions>
      <RouterLink to="/works">
        <Button variant="soft" size="sm">回到作品列表</Button>
      </RouterLink>
    </template>
  </Empty>
</template>
