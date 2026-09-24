<script setup lang="ts">
/**
 * 作品列表 —— **也就是「全部」那一页**(地址 /works 不带类型;选了类型就是那一类)。**能改变「看到什么」的东西都写进地址**
 * —— 搜什么、第几页、按什么排:输入都改地址,再由地址驱动一次请求,所以刷新或把地址发给别人看到的是同一页。
 * 顶上的类型在外壳上(App.vue),**它同时决定这一页画什么**:形状、顺序、第几页全由后端定(`app/listing.py`),这里只画。
 */
import { computed, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import { Alert, Empty, Pagination, SegmentedControl, Spinner, Text } from "../ui";

import { ApiError, editions, works as worksApi } from "../api";
import { labelOf } from "../mediaTypes";
import { WORK_SORTS, type EditionListOut, type WorkListOut } from "../types";
import { useReloadOnReturn } from "../useLoad";
import CarrierRow from "../components/CarrierRow.vue";
import ListHeader from "../components/ListHeader.vue";
import WorkRow from "../components/WorkRow.vue";

/** 这一页留在内存里(见 App.vue 的 KeepAlive 名单),两边要一致。 */
defineOptions({ name: "WorksList" });

const route = useRoute();
const router = useRouter();

/**
 * **两行东西,取决于顶上选没选类型**(见 App.vue):没选类型取 `/api/works`(一行一个**作品总标题**),选了类型取 `/api/editions?media_type=…`
 * (一行一份**作品**,收窄到那一类)。两种形状分开存、分开画 —— **不能只换页头那个标题**,那样选了类型之后列表照旧取 `/api/works`。
 */
const works = ref<WorkListOut | null>(null);
const carriers = ref<EditionListOut | null>(null);

const error = ref("");
const loading = ref(false);

const keyword = computed(() => (route.query.q as string) ?? "");
const sort = computed(() => (route.query.sort as string) || WORK_SORTS[0].value);
const page = computed(() => Number(route.query.page ?? 1) || 1);
const mediaType = computed(() => (route.query.media_type as string) ?? "");

/** 顶上选了某一类没有。列表形状、页头的话、空状态的话都跟着它走。 */
const byType = computed(() => mediaType.value !== "");

/** 现在画的是哪一份列表(两份里只有一份在);页头计数、翻页、那句「拼写相近」都读它。 */
const list = computed(() => works.value ?? carriers.value);

/** 有关键词时默认档实际是「相关度优先、标题消歧」,界面必须把这件事说准。 */
const sortOptions = computed(() =>
  WORK_SORTS.map((option) => ({
    ...option,
    label: keyword.value
      ? option.value === "title"
        ? "按相关"
        : "相关内按时间"
      : option.label,
  })),
);

const listTitle = computed(() => (byType.value ? labelOf(mediaType.value) : "全部作品"));

const listNote = computed(() => {
  if (!list.value) return "";
  const unit = byType.value ? "份" : "条";
  return keyword.value ? `搜到 ${list.value.total} ${unit}` : `共 ${list.value.total} ${unit}`;
});

/** 换排序、翻页都从这里走:地址一变,上面那几个 computed 跟着变,watch 再取一次。 */
function go(changes: Record<string, string | number | undefined>) {
  const next: Record<string, string | number | undefined> = {
    q: keyword.value || undefined,
    sort: sort.value === WORK_SORTS[0].value ? undefined : sort.value,
    media_type: mediaType.value || undefined,
    page: page.value > 1 ? page.value : undefined,
    ...changes,
  };
  router.push({ path: "/works", query: next as never });
}

async function load({ silent = false }: { silent?: boolean } = {}) {
  // 悄悄取:已经画好的那一屏先留着(退回来时用),不换成一行「正在读取」
  if (!silent) loading.value = true;
  error.value = "";
  const shared = {
    q: keyword.value || undefined,
    sort: sort.value === WORK_SORTS[0].value ? undefined : sort.value,
    page: page.value > 1 ? page.value : undefined,
  };
  try {
    if (byType.value) {
      carriers.value = await editions.list({ ...shared, media_type: mediaType.value });
      works.value = null;
    } else {
      works.value = await worksApi.list(shared);
      carriers.value = null;
    }
  } catch (failure) {
    works.value = null;
    carriers.value = null;
    error.value = failure instanceof ApiError ? failure.message : String(failure);
  } finally {
    if (!silent) loading.value = false;
  }
}

// immediate:第一次进来也要取一次。之后地址一变就重取。
watch(() => route.fullPath, () => load(), { immediate: true });
// 这一页被缓存着:退回来时先把原来那一屏显示出来,同时悄悄取一次新的(位置留住,数据不过期)。
useReloadOnReturn(() => void load({ silent: true }));
</script>

<template>
  <div class="flex flex-col gap-5">
    <ListHeader :title="listTitle" :note="listNote">
      <template #tools>
        <div class="flex items-center gap-2">
          <Text size="sm" tone="muted">排序</Text>
          <SegmentedControl
            :model-value="sort"
            :options="sortOptions"
            size="sm"
            @update:model-value="(value) => go({ sort: String(value), page: undefined })"
          />
        </div>
      </template>
    </ListHeader>

    <Alert v-if="error" tone="danger" title="没能读到列表">{{ error }}</Alert>
    <Alert v-else-if="list?.approximate" tone="info">
      未找到完全匹配的结果,以下为拼写相近的条目。
    </Alert>

    <div v-if="loading" class="flex items-center gap-2 py-6 text-muted">
      <Spinner size="sm" />
      <Text size="sm" tone="muted">正在读取…</Text>
    </div>

    <template v-else-if="list">
      <ul v-if="works?.items.length" class="flex flex-col divide-y divide-line">
        <WorkRow v-for="work in works.items" :key="work.id" :work="work" />
      </ul>

      <ul v-else-if="carriers?.items.length" class="flex flex-col divide-y divide-line">
        <CarrierRow v-for="edition in carriers.items" :key="edition.id" :edition="edition" />
      </ul>

      <Empty v-else-if="keyword" title="没有找到" :description="`未找到「${keyword}」。`" />
      <Empty
        v-else-if="byType"
        title="这一类下还没有作品"
        :description="`还没有登记过${labelOf(mediaType)}。`"
      />
      <!--
        新增入口只有顶栏右上角那一枚「+」(加入作品);空库时在页面里指一下,免得这一页看上去无处可去。
        **那一枚一直在**,所以这一句也跟着一直在。
      -->
      <template v-else>
        <Empty title="还没有记录" description="这个库里还没有作品。" />
        <Text size="sm" tone="muted">
          点右上角的「+」可以从外部数据源找一部作品加进来。
        </Text>
      </template>

      <Pagination
        :model-value="list.page"
        :total="list.total"
        :item-count="list.page_size"
        align="end"
        hide-single-page
        @update:model-value="(value) => go({ page: Number(value) })"
      />
    </template>
  </div>
</template>
