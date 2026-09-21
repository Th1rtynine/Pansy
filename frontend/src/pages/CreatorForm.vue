<script setup lang="ts">
/**
 * 改一位作者的名字与别名。**改成另一个已有的名字是合并,不是冲突** —— 引用挪过去、空出来的那条删掉、被并掉的名字进别名(规矩在后端 `app/rules.py`)。
 */
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import { Alert, Button, Center, FormField, Heading, Input, Spinner, TagsInput, Text } from "../ui";
import FormPage from "../components/FormPage.vue";
import FormSection from "../components/FormSection.vue";

import { creators } from "../api";
import { messageOf, useLoad } from "../useLoad";

const route = useRoute();
const router = useRouter();
const creatorId = computed(() => Number(route.params.id));

const form = ref({ name: "", aliases: [] as string[] });
const error = ref("");
const saving = ref(false);

const { data, error: loadError, loading } = useLoad(
  () => creators.get(creatorId.value),
  () => route.fullPath,
);

watch(data, (loaded) => {
  if (!loaded) return;
  form.value = { name: loaded.name, aliases: [...loaded.aliases] };
});

async function save() {
  saving.value = true;
  error.value = "";
  try {
    await creators.rename(creatorId.value, form.value);
    router.push(`/creators/${creatorId.value}`);
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
    :title="`编辑作者 · ${data?.name ?? ''}`"
    description="作者是全库共用的词:改一次名字,所有引用它的地方跟着改。"
    :saving="saving"
    :cancel-to="`/creators/${creatorId}`"
    @submit="save"
  >
    <template #alerts>
      <Alert v-if="loadError" tone="danger" title="读不到这一位">{{ loadError }}</Alert>
      <Alert v-if="error" tone="danger" title="没能保存">{{ error }}</Alert>
    </template>

    <FormSection title="这一位作者">
      <FormField label="名字" description="必填;改成另一个已有的名字就是合并两条" required>
        <Input v-model="form.name" />
      </FormField>
      <FormField label="别名" description="输入后回车。搜索认别名:敲笔名也能找到这里">
        <TagsInput v-model="form.aliases" />
      </FormField>

      <Text size="sm" tone="faint">
              </Text>
    </FormSection>
  </FormPage>
</template>
