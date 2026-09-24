<script setup lang="ts">
/** 编辑一卷。保存与删除之后都回到所属作品的编辑页 —— 那才是读者刚才在弄的那一页。 */
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  Alert,
  Button,
  Center,
  Cover,
  FormField,
  Heading,
  Input,
  NumberInput,
  Popconfirm,
  Spinner,
  Text,
  Textarea,
} from "../ui";

import { volumes } from "../api";
import FormPage from "../components/FormPage.vue";
import FormSection from "../components/FormSection.vue";
import { messageOf, useLoad } from "../useLoad";
import type { VolumeIn } from "../types";

const route = useRoute();
const router = useRouter();
const volumeId = computed(() => Number(route.params.id));

const form = ref<VolumeIn>({ volume_number: null, title: "", summary: "", published_on: "" });
const error = ref("");
const saving = ref(false);

const { data, error: loadError, loading } = useLoad(
  () => volumes.get(volumeId.value),
  () => route.fullPath,
);

watch(data, (loaded) => {
  if (!loaded) return;
  form.value = {
    volume_number: loaded.volume_number,
    title: loaded.title ?? "",
    summary: loaded.summary ?? "",
    published_on: loaded.published_on ?? "",
    catalog_code: loaded.catalog_code ?? "",
    page_count: loaded.page_count,
    volume_type: loaded.volume_type ?? "",
    local_path: loaded.local_path ?? "",
  };
});

async function save() {
  saving.value = true;
  error.value = "";
  try {
    await volumes.update(volumeId.value, form.value);
    router.push(`/editions/${data.value?.edition_id ?? 0}/edit`);
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    saving.value = false;
  }
}

async function remove() {
  await volumes.remove(volumeId.value);
  router.push(`/editions/${data.value?.edition_id ?? 0}/edit`);
}

/**
 * 封面:选一张就立刻传上去。**它不进这张表单的保存** —— 与作品的封面同一路,点了就生效,
 * 所以传完不必刷新页面,把回来的那一份填回本地即可(尺寸也要填:它说的是刚传的这一个文件)。
 */
const uploadingCover = ref(false);
const notice = ref("");

async function uploadCover(event: Event) {
  const input = event.target as HTMLInputElement;
  const chosen = input.files?.[0];
  if (!chosen) return;
  uploadingCover.value = true;
  error.value = "";
  notice.value = "";
  try {
    const body = new FormData();
    body.append("file", chosen);
    const answer = await fetch(`/api/volumes/${volumeId.value}/cover`, { method: "POST", body });
    const payload = await answer.json();
    if (!answer.ok) {
      error.value = String(payload?.detail ?? "没能上传封面。");
      return;
    }
    if (data.value) {
      data.value.cover_url = payload.cover_url;
      data.value.cover_width = payload.cover_width;
      data.value.cover_height = payload.cover_height;
    }
    notice.value = "封面换好了。";
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : String(failure);
  } finally {
    uploadingCover.value = false;
    input.value = ""; // 同一个文件再选一次也要能触发 change
  }
}

async function dropCover() {
  error.value = "";
  notice.value = "";
  const answer = await fetch(`/api/volumes/${volumeId.value}/cover`, { method: "DELETE" });
  const payload = await answer.json();
  if (!answer.ok) {
    error.value = String(payload?.detail ?? "没能摘掉封面。");
    return;
  }
  if (data.value) {
    data.value.cover_url = payload.cover_url;
    data.value.cover_width = payload.cover_width;
    data.value.cover_height = payload.cover_height;
  }
  notice.value = "封面摘掉了。";
}
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>

  <FormPage
    v-else
    title="编辑这一条"
    description="这一卷的序号、名字与简介。"
    :saving="saving"
    :cancel-to="`/editions/${data?.edition_id ?? 0}/edit`"
    @submit="save"
  >
    <template #alerts>
      <Alert v-if="loadError" tone="danger" title="读不到这一条">{{ loadError }}</Alert>
      <Alert v-if="error" tone="danger" title="没能完成">{{ error }}</Alert>
      <Alert v-if="notice" tone="success">{{ notice }}</Alert>
    </template>

    <FormSection title="这一卷">
      <FormField label="序号" description="可以是 4.5 这样插在两卷之间的号;留空表示没有序号">
        <NumberInput v-model="form.volume_number" :step="0.5" class="w-32" />
      </FormField>
      <FormField label="名字">
        <Input v-model="form.title" />
      </FormField>
      <FormField label="发售日期"><Input v-model="form.published_on" /></FormField>
      <FormField label="ISBN / 编号"><Input v-model="form.catalog_code" /></FormField>
      <FormField label="页数"><NumberInput v-model="form.page_count" :min="0" /></FormField>
      <FormField label="分卷类型"><Input v-model="form.volume_type" /></FormField>
      <FormField label="本地资源"><Input v-model="form.local_path" class="font-mono" /></FormField>
    </FormSection>

    <FormSection title="说了什么">
      <FormField label="简介">
        <Textarea v-model="form.summary" :rows="4" />
      </FormField>
    </FormSection>

    <FormSection
      title="封面"
      description="这一卷自己的封面:选一张就传上去,不必再按保存。"
    >
      <div class="flex flex-wrap items-start gap-4">
        <Cover
          :title="data?.title || '卷'"
          :src="data?.cover_url ?? null"
          :width="data?.cover_width ?? null"
          :height="data?.cover_height ?? null"
          size="hero"
        />
        <div class="flex flex-col gap-2">
          <!-- 文件选择框用浏览器自己的:拖拽、手机相册、键盘操作都是现成的 -->
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            :disabled="uploadingCover"
            class="text-sm text-muted file:mr-3 file:cursor-pointer file:rounded-control file:border file:border-line file:bg-surface file:px-3 file:py-1.5 file:text-sm file:text-fg"
            @change="uploadCover"
          />
          <Text size="sm" tone="faint">
            JPEG、PNG、WebP 或 GIF,最大 8 MB。
          </Text>
          <div v-if="data?.cover_url">
            <Button variant="ghost" tone="danger" size="sm" type="button" @click="dropCover">
              摘掉封面
            </Button>
          </div>
        </div>
      </div>
    </FormSection>

    <!-- 删除不是「保存」的一部分,但它和保存一样是这一页的动作,所以排在同一条线上 -->
    <template #actions>
      <Popconfirm
        title="删除这一条?"
        description="数据库记录不会保留。"
        tone="danger"
        confirm-text="删除"
        :on-confirm="remove"
      >
        <Button variant="soft" tone="danger" type="button">删除这一条</Button>
      </Popconfirm>
    </template>
  </FormPage>
</template>
