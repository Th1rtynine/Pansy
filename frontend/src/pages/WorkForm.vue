<script setup lang="ts">
/**
 * 新建作品、以及编辑一件作品总标题。两种用法放在一个文件里,因为它们改的是同一批字段,分开写就会有两份。
 *
 * 新建时总标题与第一份作品一次填完:接口是两条(`POST /works` 再 `POST /works/{id}/editions`),这里按顺序发两次;
 * 第二次失败会停在原地并说明记录已经建好(空的总标题是允许状态,列表上写着「尚未建立作品」,点进去能补)。
 */
import { computed, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  Alert,
  Button,
  Center,
  FormField,
  Input,
  Popconfirm,
  Spinner,
  TagsInput,
} from "../ui";

import { editions, works } from "../api";
import { fieldsOf, mediaTypes } from "../mediaTypes";
import { messageOf, useLoad } from "../useLoad";
import { useUnsavedChanges } from "../useUnsavedChanges";
import type { EditionIn, WorkIn } from "../types";
import CarrierFields from "../components/CarrierFields.vue";
import FormPage from "../components/FormPage.vue";
import FormSection from "../components/FormSection.vue";
import WorkEditNav from "../components/WorkEditNav.vue";

const route = useRoute();
const router = useRouter();

const editingId = computed(() => (route.params.id ? Number(route.params.id) : 0));
const isEditing = computed(() => editingId.value > 0);

const workForm = ref<WorkIn>({ title: "", original_title: "", aliases: [] });
const carrierForm = ref<EditionIn>(emptyCarrier());
const error = ref("");
const saving = ref(false);
/** 新建时第二次请求失败留下的那句话:记录已经建好,只差那一份作品。 */
const createdId = ref(0);

function formSnapshot(): string {
  return JSON.stringify({ work: workForm.value, carrier: carrierForm.value });
}

const savedSnapshot = ref(formSnapshot());
const isDirty = computed(() => formSnapshot() !== savedSnapshot.value);
useUnsavedChanges(isDirty);

function emptyCarrier(): EditionIn {
  return {
    media_type: mediaTypes.value[0]?.value ?? "manga",
    title: "",
    published_on: "",
    summary: "",
    org: "",
    release_status: "",
    volume_count: null,
    creators: [],
    tags: [],
  };
}

const spec = computed<Record<string, string>>(() =>
  isEditing.value ? {} : fieldsOf(carrierForm.value.media_type),
);

// 编辑时把这一条读进来填好;新建时不读。
const { data, error: loadError, loading } = useLoad(
  async () => (isEditing.value ? works.get(editingId.value) : null),
  () => route.fullPath,
);

watch(data, (loaded) => {
  if (!loaded) return;
  workForm.value = {
    title: loaded.title,
    original_title: loaded.original_title ?? "",
    aliases: [...loaded.aliases],
  };
  savedSnapshot.value = formSnapshot();
});

function editionNavDetail(edition: NonNullable<typeof data.value>["editions"][number]): string {
  const title = edition.title?.trim() || "使用总标题";
  const names = [...new Set(edition.creators.map((creator) => creator.name.trim()).filter(Boolean))];
  if (!names.length) return title;
  const shown = names.slice(0, 2).join("、");
  return `${title} · ${shown}${names.length > 2 ? " 等" : ""}`;
}

const editNavItems = computed(() => {
  const loaded = data.value;
  if (!loaded) return [];
  return [
    { key: "work", label: "作品信息", detail: loaded.title },
    ...loaded.editions.map((edition) => ({
      key: `edition-${edition.id}`,
      label: edition.media_label,
      detail: editionNavDetail(edition),
      to: `/editions/${edition.id}/edit`,
    })),
  ];
});

const uploadingCover = ref(false);

/**
 * 总标题自己的封面:选一张就传,传完立刻生效(不必再按保存);摘掉只清数据库那一列,硬盘上的文件留着。
 * 没传过时读取那一侧沿用第一件的封面(见后端 `work_out`),所以页面上永远不会因此变空白。
 */
async function pickWorkCover(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file || !data.value) return;
  uploadingCover.value = true;
  try {
    applyWorkCover(await works.uploadCover(data.value.id, file));
  } catch (failure) {
    error.value = `没能存下这张图:${messageOf(failure)}`;
  } finally {
    uploadingCover.value = false;
  }
}

async function dropWorkCover(): Promise<void> {
  if (!data.value) return;
  uploadingCover.value = true;
  try {
    applyWorkCover(await works.clearCover(data.value.id));
  } catch (failure) {
    error.value = `没能摘掉这张图:${messageOf(failure)}`;
  } finally {
    uploadingCover.value = false;
  }
}

/** 接口回来的封面那三样盖到这一页上;别的字段不动 —— 那几个格子是人在编辑的。 */
function applyWorkCover(answer: {
  cover_url: string | null;
  cover_width: number | null;
  cover_height: number | null;
}): void {
  if (!data.value) return;
  data.value.cover_url = answer.cover_url;
  data.value.cover_width = answer.cover_width;
  data.value.cover_height = answer.cover_height;
}

async function save() {
  saving.value = true;
  error.value = "";
  try {
    if (isEditing.value) {
      await works.update(editingId.value, workForm.value);
      savedSnapshot.value = formSnapshot();
      router.push(`/works/${editingId.value}`);
      return;
    }

    const created = await works.create(workForm.value);
    createdId.value = created.id;
    try {
      await editions.create(created.id, carrierForm.value);
    } catch (failure) {
      error.value = `作品总标题已经建好了,但第一份作品没写进去:${messageOf(failure)}`;
      return;
    }
    savedSnapshot.value = formSnapshot();
    router.push(`/works/${created.id}`);
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    saving.value = false;
  }
}

async function remove() {
  await works.remove(editingId.value);
  savedSnapshot.value = formSnapshot();
  router.push("/works");
}
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>

  <FormPage
    v-else
    :title="isEditing ? `编辑作品总标题 · ${data?.title ?? ''}` : '新建作品'"
    description="这部作品的名字、原名与别名。"
    :saving="saving"
    :cancel-to="isEditing ? `/works/${editingId}` : '/works'"
    @submit="save"
  >
    <template #alerts>
      <Alert v-if="loadError" tone="danger" title="读不到这一条">{{ loadError }}</Alert>
      <Alert v-if="error" tone="danger" title="没能保存">{{ error }}</Alert>
      <Alert v-if="createdId" tone="info" title="记录已经建好了">
        这一条已经在库里(还没有作品)。
        <RouterLink class="text-accent-text" :to="`/works/${createdId}/editions/new`">
          去给它添加一份作品
        </RouterLink>
        ,或者
        <RouterLink class="text-accent-text" :to="`/works/${createdId}`">打开它</RouterLink>。
      </Alert>
    </template>

    <div :class="isEditing ? 'grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start' : ''">
      <!-- 左栏最上面是总标题自己的封面,位置与写法跟「编辑一件」那一页的左栏一样;sticky 要写在**这一层包壳**上,写在里面的组件上就跟不动页面。 -->
      <div v-if="isEditing" class="flex min-w-0 flex-col gap-3 lg:sticky lg:top-24">
        <div class="flex flex-col gap-2">
          <img
            v-if="data?.cover_url"
            :src="data.cover_url"
            alt=""
            class="aspect-[3/4] w-full rounded-card border border-line object-cover"
          />
          <span
            v-else
            class="block aspect-[3/4] w-full rounded-card border border-line bg-inset"
          ></span>
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            :disabled="uploadingCover"
            class="w-full text-xs text-muted file:mr-2 file:cursor-pointer file:rounded-control file:border file:border-line file:bg-surface file:px-2 file:py-1 file:text-xs file:text-fg"
            @change="pickWorkCover"
          />
          <p class="text-xs text-faint">
            JPEG、PNG、WebP 或 GIF,最大 8 MB。选一张就传上去,不必再按保存。没传过时用的是第一件的封面。
          </p>
          <div v-if="data?.cover_url">
            <Button variant="ghost" tone="danger" size="sm" type="button" @click="dropWorkCover">
              摘掉封面
            </Button>
          </div>
        </div>

        <WorkEditNav
          v-if="data"
          :items="editNavItems"
          active="work"
          :add-to="`/works/${editingId}/editions/new`"
        />
      </div>

      <div class="min-w-0">
        <FormSection title="作品总标题信息" description="这里的名称由所有类型共用;选择左侧的一项可进入它自己的编辑页。">
          <FormField label="作品总标题" description="必填" required>
            <Input v-model="workForm.title" />
          </FormField>
          <FormField label="原名" description="原文语言的写法,没有单独写法则留空">
            <Input v-model="workForm.original_title" />
          </FormField>
          <FormField label="别名" description="输入后回车;搜索认别名">
            <TagsInput v-model="workForm.aliases" />
          </FormField>
        </FormSection>

        <FormSection
          v-if="!isEditing"
          title="作品信息"
          description="类型决定这一份作品有哪些字段,所以先选类型;换类型会清空下面已填的内容。"
        >
          <CarrierFields v-model="carrierForm" :spec="spec" show-type />
        </FormSection>
      </div>
    </div>

    <template #after>
      <template v-if="isEditing && data">
        <FormSection title="删除" description="将删除该作品总标题及其全部作品与卷。">
          <Popconfirm
            title="删除这个作品总标题?"
            description="它下面的全部作品和卷也会一起删掉。数据库记录不会保留。"
            tone="danger"
            confirm-text="删除"
            :on-confirm="remove"
          >
            <Button variant="soft" tone="danger" size="sm">删除这个作品总标题</Button>
          </Popconfirm>
        </FormSection>
      </template>
    </template>
      <!-- **这一部有哪几件:一面图墙**。只有总标题那三个字段时,「有哪几件」只出现在左边那条窄目录里,认不出是哪一件。
      断点与件里面那面卷墙一致(**窄屏三列、sm 四列、2xl 六列**);它是链接、不提交表单,所以并进表单区里。 -->
    <section v-if="loaded && loaded.editions.length" class="flex flex-col gap-3">
        <div class="flex items-center gap-2">
          <h2 class="text-base font-medium">这一部有哪几件</h2>
          <span class="text-sm text-faint">{{ loaded.editions.length }} 件</span>
          <span class="h-px flex-1 bg-line"></span>
        </div>

        <ul class="grid min-w-0 grid-cols-3 gap-2 sm:grid-cols-4 2xl:grid-cols-6">
          <li v-for="edition in loaded.editions" :key="edition.id" class="min-w-0">
            <RouterLink
              :to="`/editions/${edition.id}/edit`"
              class="flex min-w-0 flex-col gap-2 rounded-card border border-line bg-surface p-2 transition-colors hover:border-accent/50 hover:bg-state-hover active:bg-state-press"
            >
              <img
                v-if="edition.cover_url"
                :src="edition.cover_url"
                alt=""
                loading="lazy"
                class="aspect-[3/4] w-full rounded-control border border-line object-cover"
              />
              <span
                v-else
                class="block aspect-[3/4] w-full rounded-control border border-line bg-inset"
              ></span>

              <span class="flex min-w-0 flex-col gap-0.5">
                <span class="truncate text-sm">{{ edition.title || edition.media_label }}</span>
                <span class="flex flex-wrap items-center gap-x-1.5 text-xs text-faint">
                  <span>{{ edition.media_label }}</span>
                  <span v-if="edition.published_on">{{ edition.published_on }}</span>
                  <span v-if="edition.volumes && edition.volumes.length">
                    {{ edition.volumes.length }} 卷
                  </span>
                </span>
              </span>
            </RouterLink>
          </li>
        </ul>
      </section>
</FormPage>
</template>
