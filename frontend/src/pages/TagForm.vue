<script setup lang="ts">
/**
 * 重命名一个标签。**类型不在这里改** —— 它决定哪些作品能挂它,改了就会出现挂在别的类型作品上的标签;所以只印出来不给改,接口也不收这个字段。
 */
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, Button, Center, FormField, Heading, Input, Spinner, Text } from "../ui";
import FormPage from "../components/FormPage.vue";
import FormSection from "../components/FormSection.vue";

import { tags } from "../api";
import { messageOf, useLoad } from "../useLoad";

const route = useRoute();
const router = useRouter();
const tagId = computed(() => Number(route.params.id));

const name = ref("");
const error = ref("");
const saving = ref(false);

const { data, error: loadError, loading } = useLoad(
  () => tags.get(tagId.value),
  () => route.fullPath,
);

watch(data, (loaded) => {
  if (loaded) name.value = loaded.name;
});

async function save() {
  saving.value = true;
  error.value = "";
  try {
    await tags.rename(tagId.value, name.value);
    router.push(`/tags/${tagId.value}`);
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    saving.value = false;
  }
}
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>

  <FormPage
    v-else
    :title="`重命名标签 · ${data?.name ?? ''}`"
    description="标签只在同一个类型里共用:漫画的「奇幻」与动画的「奇幻」是两条。"
    :saving="saving"
    :cancel-to="`/tags/${tagId}`"
    @submit="save"
  >
    <template #alerts>
      <Alert v-if="loadError" tone="danger" title="读不到这个标签">{{ loadError }}</Alert>
      <Alert v-if="error" tone="danger" title="没能保存">{{ error }}</Alert>
    </template>

    <FormSection title="这个标签">
      <FormField v-if="data" label="类型">
        <Text size="sm">{{ data.media_label }} · 建好之后不能改</Text>
      </FormField>
      <FormField label="名字" description="必填;改成同一类型下已有的名字就是合并两条" required>
        <Input v-model="name" />
      </FormField>
    </FormSection>
  </FormPage>
</template>
