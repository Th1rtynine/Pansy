<script setup lang="ts">
/**
 * 给一件作品加一份作品,以及编辑一份已有的作品。字段、作者、标签在这里收齐;卷与关联作品是
 * 各自独立的小表单(表单不能嵌套)。**类型只印出来不能改**(新建时选一次):它决定有哪些字段、
 * 内部那些行叫什么、允许挂哪些标签;交上去的 `media_type` 接口也忽略。
 */
import { computed, onMounted, ref, watch } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  Alert,
  Button,
  Center,
  FormField,
  Heading,
  Input,
  NumberInput,
  Textarea,
  Popconfirm,
  Select,
  Spinner,
  Cover,
  Text,
} from "../ui";

import { editions, sources, volumes, works } from "../api";
import { fieldsOf, labelOf } from "../mediaTypes";
import { applySuggestions } from "../prefill";
import { labelOfSource } from "../sourceNames";
import { messageOf, useLoad } from "../useLoad";
import { useUnsavedChanges } from "../useUnsavedChanges";
import type {
  EditionIn,
  EditionRef,
  SourceCandidate,
  SourceRefOut,
  SourceSuggestion,
  VolumeIn,
  VolumeOut,
  WorkDetailOut,
} from "../types";
import CarrierFields from "../components/CarrierFields.vue";
import FormPage from "../components/FormPage.vue";
import FormSection from "../components/FormSection.vue";
import WorkEditNav from "../components/WorkEditNav.vue";

const route = useRoute();
const router = useRouter();

/**
 * 编辑哪一件。**默认从地址里认**(`/editions/{id}/edit`),也可以由外面点名传进来 —— 挂在「编辑总标题」那一页的件卡里就地展开时,地址栏里没有这一件的 id。
 */
const props = withDefaults(defineProps<{ editionId?: number }>(), { editionId: 0 });

const editingId = computed(() => props.editionId || (route.params.id ? Number(route.params.id) : 0));
const isEditing = computed(() => editingId.value > 0);
const workId = computed(() => Number(route.params.workId ?? 0));

const form = ref<EditionIn>(emptyCarrier());
const error = ref("");
const notice = ref("");
const saving = ref(false);
const parentWork = ref<WorkDetailOut | null>(null);
/** 当前表单装的是哪一件;同一件的卷/关联刷新不能覆盖尚未保存的草稿。 */
const loadedEditionId = ref(0);

const candidates = ref<EditionRef[]>([]);
const chosen = ref("");
const volumeRows = ref<VolumeOut[]>([]);
const newVolume = ref<VolumeIn>({ volume_number: null, title: "", summary: "", published_on: "" });

/**
 * 卷卡**就地展开**:一次只开一张。草稿是「打开时照抄一份」—— `PUT /volumes/{id}` 是整条覆盖,少送一格那一格就被写成空,所以四个格子都要带上原值。
 */
const openVolumeId = ref<number | null>(null);
const volumeDraft = ref<VolumeIn | null>(null);
const savingVolume = ref(false);

function toggleVolume(volume: VolumeOut): void {
  if (openVolumeId.value === volume.id) {
    openVolumeId.value = null;
    volumeDraft.value = null;
    return;
  }
  openVolumeId.value = volume.id;
  volumeDraft.value = {
    volume_number: volume.volume_number,
    title: volume.title ?? "",
    summary: volume.summary ?? "",
    published_on: volume.published_on ?? "",
  };
}

async function saveVolume(volume: VolumeOut): Promise<void> {
  if (!volumeDraft.value) return;
  savingVolume.value = true;
  try {
    const answer = await volumes.update(volume.id, volumeDraft.value);
    volume.volume_number = answer.volume_number;
    volume.title = answer.title;
    volume.summary = answer.summary;
    volume.published_on = answer.published_on;
    openVolumeId.value = null;
    volumeDraft.value = null;
  } finally {
    savingVolume.value = false;
  }
}

function applyCover(volume: VolumeOut, answer: VolumeOut): void {
  volume.cover_url = answer.cover_url;
  volume.cover_width = answer.cover_width;
  volume.cover_height = answer.cover_height;
}

/**
 * 选一张图就传上去(`POST /volumes/{id}/cover`,multipart);传完先把输入框清空,否则同一张图再选一次不触发 `change`。封面与那四个格子是两条路,这边传完立刻生效。
 */
async function pickVolumeCover(volume: VolumeOut, event: Event): Promise<void> {
  const input = event.target as HTMLInputElement;
  const file = input.files?.[0];
  input.value = "";
  if (!file) return;
  savingVolume.value = true;
  try {
    applyCover(volume, await volumes.uploadCover(volume.id, file));
  } catch (failure) {
    error.value = `没能存下这张图:${messageOf(failure)}`;
  } finally {
    savingVolume.value = false;
  }
}

/** 摘掉卷封面(硬盘上的文件留着)。**名字带 volume** —— 这一页另有一个 `dropCover` 管作品封面。 */
async function dropVolumeCover(volume: VolumeOut): Promise<void> {
  savingVolume.value = true;
  try {
    applyCover(volume, await volumes.clearCover(volume.id));
  } catch (failure) {
    error.value = `没能摘掉这张图:${messageOf(failure)}`;
  } finally {
    savingVolume.value = false;
  }
}
const runFrom = ref<number | null>(null);
const runTo = ref<number | null>(null);

function emptyCarrier(): EditionIn {
  return {
    media_type: "manga",
    title: "",
    published_on: "",
    ended_on: "",
    subtype: "",
    region: "",
    language: "",
    catalog_code: "",
    homepage: "",
    engine: "",
    audience: "",
    reading_mode: "",
    content_notice: "",
    platforms: [],
    organizations: [],
    official_links: [],
    summary: "",
    org: "",
    release_status: "",
    volume_count: null,
    local_path: "",
    creators: [],
    tags: [],
  };
}

function formSnapshot(): string {
  return JSON.stringify(form.value);
}

const savedSnapshot = ref(formSnapshot());
const isDirty = computed(() => formSnapshot() !== savedSnapshot.value);
useUnsavedChanges(isDirty);

/** 编辑时用这一份自己的类型;新建时由表单里的下拉决定。 */
const mediaType = computed(() => form.value.media_type);
const spec = computed(() => fieldsOf(mediaType.value));
const unit = computed(() => spec.value.unit || "卷");

const { data, error: loadError, loading, reload } = useLoad(
  async () => (isEditing.value ? editions.get(editingId.value) : null),
  () => route.fullPath,
);

watch(data, (loaded) => {
  if (!loaded) return;
  const sameEdition = loaded.id === loadedEditionId.value;
  const keepDraft = sameEdition && isDirty.value;
  if (!keepDraft) {
    form.value = {
      media_type: loaded.media_type,
      title: loaded.title ?? "",
      published_on: loaded.published_on ?? "",
      ended_on: loaded.ended_on ?? "",
      summary: loaded.summary ?? "",
      org: loaded.org ?? "",
      release_status: loaded.release_status ?? "",
      volume_count: loaded.volume_count,
      local_path: loaded.local_path ?? "",
      subtype: loaded.subtype ?? "",
      region: loaded.region ?? "",
      language: loaded.language ?? "",
      catalog_code: loaded.catalog_code ?? "",
      homepage: loaded.homepage ?? "",
      engine: loaded.engine ?? "",
      audience: loaded.audience ?? "",
      reading_mode: loaded.reading_mode ?? "",
      content_notice: loaded.content_notice ?? "",
      platforms: [...loaded.platforms],
      organizations: loaded.organizations.map((item) => ({ ...item })),
      official_links: loaded.official_links.map((item) => ({ ...item })),
      creators: loaded.creators.map((creator) => ({ name: creator.name, role: creator.role })),
      tags: loaded.tags.map((tag) => tag.name),
    };
    savedSnapshot.value = formSnapshot();
  }
  loadedEditionId.value = loaded.id;
  volumeRows.value = loaded.volumes;
  // **带 `?volume=` 进来就自动展开那一卷** —— 旧地址 `/volumes/{id}/edit` 重定向到这里(见 router.ts)。
  const wanted = Number(route.query.volume ?? 0);
  if (wanted && loaded.volumes.some((volume) => volume.id === wanted)) {
    const row = loaded.volumes.find((volume) => volume.id === wanted)!;
    if (openVolumeId.value !== row.id) toggleVolume(row);
  }
  void loadCandidates();
  void loadParentWork(loaded.work_id);
});

async function loadParentWork(id: number) {
  try {
    const loaded = await works.get(id);
    if (data.value?.work_id === id) parentWork.value = loaded;
  } catch (failure) {
    error.value = `没能读取作品层级：${messageOf(failure)}`;
  }
}

function editionNavDetail(edition: WorkDetailOut["editions"][number]): string {
  const title = edition.title?.trim() || "使用总标题";
  const names = [...new Set(edition.creators.map((creator) => creator.name.trim()).filter(Boolean))];
  if (!names.length) return title;
  const shown = names.slice(0, 2).join("、");
  return `${title} · ${shown}${names.length > 2 ? " 等" : ""}`;
}

const editNavItems = computed(() => {
  const loaded = parentWork.value;
  if (!loaded) return [];
  return [
    {
      key: "work",
      label: "作品信息",
      detail: loaded.title,
      to: `/works/${loaded.id}/edit`,
    },
    ...loaded.editions.map((edition) => ({
      key: `edition-${edition.id}`,
      label: edition.media_label,
      detail: editionNavDetail(edition),
      to: `/editions/${edition.id}/edit`,
    })),
  ];
});

async function loadCandidates() {
  if (!isEditing.value) return;
  try {
    candidates.value = await editions.candidates(editingId.value);
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

async function save() {
  saving.value = true;
  error.value = "";
  notice.value = "";
  try {
    if (isEditing.value) {
      await editions.update(editingId.value, form.value);
      savedSnapshot.value = formSnapshot();
      notice.value = "已保存。";
      await reload();
      await loadCandidates();
      return;
    }
    const created = await editions.create(workId.value, form.value);
    savedSnapshot.value = formSnapshot();
    router.push(`/editions/${created.id}`);
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    saving.value = false;
  }
}

/**
 * 只重读卷这一块(`GET /editions/{id}/volumes`):走整页的 `reload()` 会把封面、关联、外部来源、左栏目录整份换掉,改一行卷屏幕上跟卷无关的地方也跟着重画。
 */
async function loadVolumes() {
  volumeRows.value = await volumes.list(editingId.value);
}

async function addVolume() {
  error.value = "";
  try {
    await volumes.add(editingId.value, [
      {
        volume_number: newVolume.value.volume_number,
        title: newVolume.value.title,
        summary: "",
        published_on: "",
      },
    ]);
    newVolume.value = { volume_number: null, title: "", summary: "", published_on: "" };
    await loadVolumes();
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

/** 连号一次加几条:从 3 到 30 就是 28 条,不必手打 28 行。 */
async function addRun() {
  const from = runFrom.value;
  const to = runTo.value;
  if (from === null || to === null || to < from) {
    error.value = "连号添加要填起点与终点,终点不能小于起点。";
    return;
  }
  error.value = "";
  try {
    const items: VolumeIn[] = [];
    for (let number = from; number <= to; number += 1) {
      items.push({ volume_number: number, title: "", summary: "", published_on: "" });
    }
    const added = await volumes.add(editingId.value, items);
    notice.value =
      `新增 ${added.added} 条${unit.value}记录。` +
      (added.skipped ? `跳过 ${added.skipped} 条序号已经存在的。` : "");
    runFrom.value = null;
    runTo.value = null;
    await loadVolumes();
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

async function dropVolume(id: number) {
  error.value = "";
  try {
    await volumes.remove(id);
    await loadVolumes();
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

async function link() {
  if (!chosen.value) return;
  error.value = "";
  try {
    await editions.link(editingId.value, Number(chosen.value));
    chosen.value = "";
    await reload();
    await loadCandidates();
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

async function unlink(otherId: number) {
  await editions.unlink(editingId.value, otherId);
  await reload();
  await loadCandidates();
}

async function remove() {
  await editions.remove(editingId.value);
  savedSnapshot.value = formSnapshot();
  router.push(`/works/${data.value?.work_id ?? workId.value}`);
}

/** 封面:选一张就立刻传上去。**它不进这张表单的保存**,和加卷、加关联的按钮一样点了就生效。 */
const uploadingCover = ref(false);

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
    const answer = await fetch(`/api/editions/${editingId.value}/cover`, { method: "POST", body });
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
  const answer = await fetch(`/api/editions/${editingId.value}/cover`, { method: "DELETE" });
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

/**
 * 外部来源那一块。**取回来的内容只落进上面那些格子**,写库还是走这一页的保存按钮,所以「外部数据只进草稿」不需要额外的东西来保证。
 */
const refs = ref<SourceRefOut[]>([]);
const prefillNote = ref("");

async function loadRefs() {
  if (!isEditing.value) return;
  try {
    refs.value = await sources.refs(editingId.value);
  } catch {
    // 读不到就当没记过,不该让它把整张表单拦住。
  }
}

onMounted(() => void loadRefs());

/** 把某一串建议落进表单,并如实说填了几格、几格没动。 */
function land(found: SourceSuggestion[], overwrite: boolean) {
  const result = applySuggestions(found, { edition: form.value }, { overwrite });
  const kept = result.kept ? `,${result.kept} 格已经有内容、没动` : "";
  const extra = result.skippedTags ? `;标签还有 ${result.skippedTags} 个没填` : "";
  prefillNote.value = `取回 ${found.length} 条,${overwrite ? "按它覆盖" : "填进"} ${result.filled} 格${kept}${extra}。`;
}

/** 按记住的那一条再取一遍。`overwrite` 为真时连已经填好的格子一起换。 */
async function refillFrom(ref: SourceRefOut, overwrite = false) {
  error.value = "";
  try {
    land(await sources.suggest([{ source: ref.source, external_id: ref.external_id }]), overwrite);
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

/** 编辑页上搜到并选中之后:先记住对应关系,再把建议落进表单。 */
async function takeFromSource(payload: { suggestions: SourceSuggestion[]; picks: SourceCandidate[] }) {
  for (const pick of payload.picks) {
    try {
      await sources.remember(editingId.value, {
        source: pick.source,
        external_id: pick.external_id,
        title: pick.title,
        url: payload.suggestions.find((item) => item.source === pick.source)?.url,
      });
    } catch (failure) {
      error.value = messageOf(failure);
    }
  }
  await loadRefs();
  land(payload.suggestions, false);
}

/**
 * 「按名字找」「按编号找」就摆在各自那一格旁边。两件都用 `collect`,区别在回来的是什么:
 * 编号 → 后端已取回(`resolved`),直接填;名字 → 一串候选,点哪一条取哪一条;取回来的只落进格子,写库还是走保存按钮。
 */
const idText = ref("");
const found = ref<SourceCandidate[]>([]);
const looking = ref(false);
/** 名字那一格空着时用作品总标题去搜 —— 多数作品的标题就是共用的那一个。 */
const nameForSearch = computed(() => form.value.title.trim() || data.value?.work_title || "");

async function look(text: string) {
  const keyword = text.trim();
  if (!keyword) return;

  looking.value = true;
  error.value = "";
  prefillNote.value = "";
  try {
    const answer = await sources.collect(keyword);
    found.value = answer.candidates.filter((item) => (item.match_score ?? 1) > 0);
    if (answer.resolved) {
      // 贴的是编号:直接取回来填上,并记下这条编号。
      await takeFromSource({
        picks: [answer.resolved],
        suggestions: await sources.suggest([
          { source: answer.resolved.source, external_id: answer.resolved.external_id },
        ]),
      });
    } else if (!found.value.length) {
      prefillNote.value = answer.candidates.length
        ? `来源返回了一些结果，但没有与「${keyword}」足够接近的条目。`
        : `所有来源都没搜到「${keyword}」。`;
    }
  } catch (failure) {
    error.value = messageOf(failure);
  } finally {
    looking.value = false;
  }
}

async function takeCandidate(candidate: SourceCandidate) {
  error.value = "";
  try {
    await takeFromSource({
      picks: [candidate],
      suggestions: await sources.suggest([
        { source: candidate.source, external_id: candidate.external_id },
      ]),
    });
  } catch (failure) {
    error.value = messageOf(failure);
  }
}

async function forgetRef(source: string) {
  await sources.forget(editingId.value, source);
  await loadRefs();
}

const candidateOptions = computed(() =>  candidates.value.map((item) => ({
    value: item.id,
    label: `${item.work_title}${item.title ? ` · ${item.title}` : ""}(${item.media_label})`,
  })),
);
</script>

<template>
  <Center v-if="loading"><Spinner /></Center>

  <FormPage
    v-else
    :title="isEditing ? `${data?.work_title || ''} · ${labelOf(mediaType)}` : '添加作品类型'"
    :description="isEditing ? '这一页只编辑并保存当前这一份作品;总标题与其它类型各自独立。' : '在这个作品总标题下添加一份漫画、动画或其它类型的作品。'"
    :saving="saving"
    :cancel-to="isEditing ? `/works/${data?.work_id ?? 0}/edit` : `/works/${workId}/edit`"
    @submit="save"
  >
    <template #alerts>
      <Alert v-if="loadError" tone="danger" title="读不到这一条">{{ loadError }}</Alert>
      <Alert v-if="error" tone="danger" title="没能完成">{{ error }}</Alert>
      <Alert v-if="notice" tone="success">{{ notice }}</Alert>
    </template>

    <div :class="isEditing ? 'grid gap-5 lg:grid-cols-[15rem_minmax(0,1fr)] lg:items-start' : ''">
      <!--
        这一整列的 sticky 写在包壳上:内层 `WorkEditNav` 挂在只有内容那么高的包壳里,sticky 没有余量可走就不跟页面。
      -->
      <div v-if="isEditing" class="flex min-w-0 flex-col gap-3 lg:sticky lg:top-24">
        <!--
          封面放在左栏最上面:横在右栏顶上时会占掉四百多像素,把标题、日期挤到下一屏;窄屏上左栏叠到正文前面,手机上封面自然排在页面最前。
        -->
        <Cover
          :title="data?.title || data?.work_title || ''"
          :src="data?.cover_url ?? null"
          :width="data?.cover_width ?? null"
          :height="data?.cover_height ?? null"
          size="card"
        />
        <div class="flex flex-col gap-1.5">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            :disabled="uploadingCover"
            class="w-full text-xs text-muted file:mr-2 file:cursor-pointer file:rounded-control file:border file:border-line file:bg-surface file:px-2 file:py-1 file:text-xs file:text-fg"
            @change="uploadCover"
          />
          <Text size="xs" tone="faint">JPEG、PNG、WebP 或 GIF,最大 8 MB。选一张就传上去,不必再按保存。</Text>
          <div v-if="data?.cover_url">
            <Button variant="ghost" tone="danger" size="sm" type="button" @click="dropCover">
              摘掉封面
            </Button>
          </div>
        </div>

        <WorkEditNav
          v-if="data && parentWork"
          :items="editNavItems"
          :active="`edition-${editingId}`"
          :add-to="`/works/${data.work_id}/editions/new`"
        />
      </div>

      <div class="flex min-w-0 flex-col gap-5">
        <FormSection
          title="这一份作品"
          description="类型决定这一份作品记哪几项、每项叫什么;建好之后类型不能改。"
        >
          <FormField v-if="isEditing" label="类型">
            <Text size="sm">{{ labelOf(mediaType) }} · 建好之后不能改</Text>
          </FormField>

          <CarrierFields v-model="form" :spec="spec" :show-type="!isEditing">
            <!-- 「按名字找」就摆在标题那一格旁边:名字(没填就用作品总标题)填完直接能点,不用去下面「外部来源」再写一遍。 -->
            <template #title-action>
              <Button
                variant="soft"
                size="sm"
                type="button"
                :disabled="looking || !nameForSearch"
                @click="look(nameForSearch)"
              >
                按名字找
              </Button>
              <Spinner v-if="looking" size="sm" />
            </template>
          </CarrierFields>
        </FormSection>
      </div>
    </div>

    <template #after>
      <template v-if="isEditing">
      <!-- 卷。只有内部行有名字的类型才有这一段:游戏一行都不记。 -->
      <FormSection
        v-if="spec.unit || volumeRows.length"
        :title="spec.unit || '卷'"
        description="一行一卷;也可以从几到几一次加多条。"
      >

        <!--
          卷这一层做成**图墙**:一行更多、卡片更小(窄屏三列、sm 四列、2xl 六列),断点与「加入作品」那张候选墙一致。**点一张就地展开它的格子**,展开后四个格子与封面都在这一页上改,不再往外跳。
        -->
        <ul
          v-if="volumeRows.length"
          class="grid min-w-0 grid-cols-3 gap-2 sm:grid-cols-4 2xl:grid-cols-6">
          <template v-for="volume in volumeRows" :key="volume.id">
            <!-- 选中的记号就是悬停那一个:只把边框转强调色,不加底色与阴影,免得卡片与旁边窗格各成一块色块。 -->
            <li
              :class="[
                'flex min-w-0 cursor-pointer flex-col gap-2 rounded-card border p-2 transition-colors',
                openVolumeId === volume.id
                  ? 'border-accent'
                  : 'border-line bg-surface hover:border-accent/50',
              ]"
              :aria-expanded="openVolumeId === volume.id"
              @click="toggleVolume(volume)"
            >
            <!-- 封面与名字都不各自挂点击:整张卡就是一个点击区,两处都挂会一次点击触发两次开合。 -->
            <span class="block">
              <img
                v-if="volume.cover_url"
                :src="volume.cover_url"
                alt=""
                loading="lazy"
                class="aspect-[3/4] w-full rounded-control border border-line object-cover"
              />
              <span
                v-else
                class="block aspect-[3/4] w-full rounded-control border border-line bg-inset"
              ></span>
            </span>

            <!--
              卡片分两块:**封面是链接**(去这一卷自己的页面),下面这一块是展开开关;不需要「编辑」按钮,这四个格子就是 `/volumes/{id}/edit` 独立页能做的全部。
            -->
            <!--
              **字直接写在卡片上**:原来是个 `<button>`,自带的底色点过之后会一直亮着;现在整张卡就是点击区。
            -->
            <span class="flex min-w-0 flex-col gap-0.5">
              <span class="truncate text-sm">
                {{
                  volume.volume_number === null
                    ? volume.title || "没有序号"
                    : `第 ${volume.volume_number} ${spec.unit || "卷"}`
                }}
              </span>
              <span
                v-if="volume.volume_number !== null && volume.title"
                class="truncate text-xs text-muted"
              >
                {{ volume.title }}
              </span>
              <span v-if="volume.published_on" class="text-xs text-faint">
                {{ volume.published_on }}
              </span>
            </span>

            <span class="mt-auto flex items-center gap-2" @click.stop>
              <Popconfirm
                title="删除这一条?"
                description="数据库记录不会保留。"
                tone="danger"
                confirm-text="删除"
                :on-confirm="() => dropVolume(volume.id)"
              >
                <Button variant="ghost" tone="danger" size="sm">删除</Button>
              </Popconfirm>
            </span>
          </li>

            <!--
              展开的那一块不是长在卡片里,而是**它旁边的一格**(占三列):卡片只有一百六十像素宽,四个格子塞进去按钮就会折行;它占了三列,后面的封面会自动顺延。
            -->
            <li
              v-if="openVolumeId === volume.id && volumeDraft"
              class="col-span-3 flex min-w-0 flex-col gap-3 p-3"
            >
              <div class="grid min-w-0 gap-3 sm:grid-cols-2 2xl:grid-cols-4">
                <FormField label="序号">
                  <NumberInput v-model="volumeDraft.volume_number" :step="0.5" />
                </FormField>
                <FormField :label="spec.name || '名字'">
                  <Input v-model="volumeDraft.title" />
                </FormField>
                <FormField label="发售日" description="写多少算多少:2006 / 2006-05 / 2006-05-24">
                  <Input v-model="volumeDraft.published_on" placeholder="2006-05-24" />
                </FormField>
                <FormField label="简介">
                  <Textarea v-model="volumeDraft.summary" :rows="3" />
                </FormField>
              </div>
              <span class="flex flex-wrap items-center gap-2">
                <Button
                  variant="solid"
                  tone="accent"
                  size="sm"
                  type="button"
                  :loading="savingVolume"
                  @click="saveVolume(volume)"
                >
                  保存这一卷
                </Button>
                <Button variant="ghost" size="sm" type="button" @click="toggleVolume(volume)">
                  收起
                </Button>
              </span>

              <!-- 封面:源里给的那张已经在卡上了,这两样是给自己扫的图留的;传一张立刻生效,不必点「保存这一卷」。 -->
              <div class="flex flex-wrap items-center gap-3 border-t border-line pt-3">
                <Text size="sm" tone="muted">
                  {{ volume.cover_url ? "封面来自源里,也可以换成本机的一张。" : "这一卷还没有封面。" }}
                </Text>
                <input
                  type="file"
                  accept="image/png,image/jpeg,image/webp,image/gif"
                  class="text-sm text-muted file:mr-2 file:rounded-control file:border file:border-line file:bg-surface file:px-2 file:py-1 file:text-sm"
                  @change="pickVolumeCover(volume, $event)"
                />
                <Button
                  v-if="volume.cover_url"
                  variant="ghost"
                  size="sm"
                  type="button"
                  :disabled="savingVolume"
                  @click="dropVolumeCover(volume)"
                >
                  摘掉封面
                </Button>
              </div>
            </li>
          </template>
        </ul>
        <Text v-else size="sm" tone="muted">暂无{{ spec.unit || "卷" }}。</Text>

        <div v-if="spec.unit" class="flex flex-wrap items-end gap-3">
          <FormField label="序号">
            <NumberInput v-model="newVolume.volume_number" :step="0.5" class="w-28" />
          </FormField>
          <FormField :label="spec.name || '名字'">
            <Input v-model="newVolume.title" class="w-56" />
          </FormField>
          <Button variant="soft" size="sm" type="button" @click="addVolume">添加一条</Button>
        </div>

        <div v-if="spec.unit" class="flex flex-wrap items-end gap-3">
          <FormField label="连号添加" description="从几到几,一次加多条">
            <div class="flex items-center gap-2">
              <NumberInput v-model="runFrom" :min="0" :step="1" class="w-24" />
              <Text size="sm" tone="muted">到</Text>
              <NumberInput v-model="runTo" :min="0" :step="1" class="w-24" />
            </div>
          </FormField>
          <Button variant="soft" size="sm" type="button" @click="addRun">连续添加</Button>
        </div>
      </FormSection>

      <FormSection
        title="关联作品"
        description="只列出还能关联的作品。"
      >

        <ul v-if="data?.relations.length" class="flex flex-col divide-y divide-line">
          <li
            v-for="other in data.relations"
            :key="other.id"
            class="flex flex-wrap items-center justify-between gap-2 py-2"
          >
            <RouterLink class="text-accent-text" :to="`/editions/${other.id}`">
              {{ other.work_title }}<template v-if="other.title"> · {{ other.title }}</template>
              <Text size="sm" tone="muted">{{ other.media_label }}</Text>
            </RouterLink>
            <Button variant="ghost" tone="danger" size="sm" @click="unlink(other.id)">
              删除关联
            </Button>
          </li>
        </ul>
        <Text v-else size="sm" tone="muted">暂无关联作品。</Text>

        <div v-if="candidateOptions.length" class="flex flex-wrap items-end gap-3">
          <FormField label="选择作品" description="只列出可以关联的">
            <Select v-model="chosen" :options="candidateOptions" class="w-80" />
          </FormField>
          <Button variant="soft" size="sm" type="button" @click="link">建立关联</Button>
        </div>
        <Text v-else size="sm" tone="faint">库中暂无其它作品可供关联。</Text>
      </FormSection>

      <!-- 外部来源:记下这条作品在别的站上是哪一条;取回来的内容只落进上面的格子,保存才写进库。 -->
      <FormSection
        title="外部来源"
        description="记下这条作品在别的站上是哪一条,以后可以按编号再取一遍。取回来的内容先落进上面的格子。"
      >
        <div v-if="refs.length" class="flex flex-col gap-2">
          <div
            v-for="ref in refs"
            :key="ref.source"
            class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-control border border-line px-2.5 py-2"
          >
            <Text size="sm">{{ labelOfSource(ref.source) }} · {{ ref.external_id }}</Text>
            <Text size="sm" tone="muted">{{ ref.title }}</Text>
            <a
              v-if="ref.url"
              class="text-sm text-accent-text"
              :href="ref.url"
              target="_blank"
              rel="noreferrer"
            >
              看原文
            </a>
            <div class="ms-auto flex flex-wrap items-center gap-2">
              <Button variant="soft" size="sm" type="button" @click="refillFrom(ref)">
                填进空格
              </Button>
              <Button variant="soft" size="sm" type="button" @click="refillFrom(ref, true)">
                覆盖已填的
              </Button>
              <Button variant="soft" tone="danger" size="sm" type="button" @click="forgetRef(ref.source)">
                忘掉
              </Button>
            </div>
          </div>
        </div>
        <Text v-else size="sm" tone="muted">
          还没有记过。贴一条编号、或者按名字找一条,选中就会记住「这条作品对应它哪一条」。
        </Text>

        <FormField
          label="编号"
          description="贴那个站上的条目编号:Bangumi 写 bgm:294993、VNDB 写 vndb:v4"
        >
          <div class="flex flex-wrap items-center gap-2">
            <Input
              v-model="idText"
              placeholder="bgm:294993 / vndb:v4"
              class="min-w-0 flex-1"
              @keydown.enter="look(idText)"
            />
            <Button
              variant="soft"
              size="sm"
              type="button"
              :disabled="looking || !idText.trim()"
              @click="look(idText)"
            >
              按编号找
            </Button>
            <Spinner v-if="looking" size="sm" />
          </div>
        </FormField>

        <!-- 名字那一路搜回来的候选:点一条就取一条填上,不设「先勾再按确认」两道手续。 -->
        <div v-if="found.length" class="flex flex-col gap-1.5">
          <Text size="sm" tone="muted">找到了这些,点一条就把它的内容取回来:</Text>
          <ul class="flex flex-col gap-1">
            <li v-for="item in found" :key="`${item.source}-${item.external_id}`">
              <button
                type="button"
                :class="[
                  'flex w-full items-center gap-2.5 rounded-control border px-2 py-1.5 text-left transition-colors',
                  refs.some((ref) => ref.source === item.source && ref.external_id === item.external_id)
                    ? 'border-accent bg-accent-soft'
                    : 'border-line hover:bg-state-hover active:bg-state-press',
                ]"
                @click="takeCandidate(item)"
              >
                <img
                  v-if="item.cover_url"
                  :src="item.cover_url"
                  alt=""
                  loading="lazy"
                  class="h-12 w-9 shrink-0 rounded-control border border-line object-cover"
                />
                <span v-else class="h-12 w-9 shrink-0 rounded-control border border-line bg-inset"></span>

                <span class="flex min-w-0 flex-1 flex-col">
                  <span class="truncate text-base">{{ item.title }}</span>
                  <span v-if="item.original_title" class="truncate text-sm text-muted">
                    {{ item.original_title }}
                  </span>
                </span>

                <Text size="sm" tone="muted">
                  {{ labelOfSource(item.source) }} {{ item.external_id }}
                  <template v-if="item.kind"> · {{ item.kind }}</template>
                  <template v-if="item.year"> · {{ item.year }}</template>
                </Text>
              </button>
            </li>
          </ul>
        </div>

        <Text v-if="prefillNote" size="sm" tone="muted">{{ prefillNote }}</Text>
      </FormSection>

      <FormSection
        title="删除"
        description="它用到的作者与标签不会被删掉。"
      >
        <Popconfirm
          title="删除这个作品?"
          :description="`${spec.unit ? `它下面的${spec.unit}也会一起删掉。` : ''}作者与标签会留在库里。数据库记录不会保留。`"
          tone="danger"
          confirm-text="删除"
          :on-confirm="remove"
        >
          <Button variant="soft" tone="danger" size="sm">删除这个作品</Button>
        </Popconfirm>
      </FormSection>
      </template>
    </template>
  </FormPage>
</template>
