<script setup lang="ts">
/**
 * 顶栏上的搜索:收起时就是一枚放大镜,点它才展开。展开的是一层浮层,顶栏里谁都不动 ——
 * 宽屏从图标位置向左长出来,窄屏挂在顶栏卡片下沿、与卡片同宽(本组件这一层写 `static`)。
 * 窄屏输入框字号必须 16px(iOS 对小输入框一聚焦就放大整页)。面板里是最近搜索与库里最多
 * 的标签。**组件不碰地址**:回车、点词、点标签都报一个 `search` 给外壳,由外壳改地址。
 */
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { CloseButton, Text } from "../ui";

import { tags } from "../api";

const props = withDefaults(defineProps<{ keyword?: string }>(), { keyword: "" });
const emit = defineEmits<{ search: [text: string] }>();

/** 最近搜索存在这里,和主题、主色同一套名字(pansy.theme / pansy.accent)。 */
const RECENT_KEY = "pansy.searches";
const RECENT_MAX = 8;

/** 面板里列几个标签:八个,再多就要滚。 */
const TAG_MAX = 8;

const expanded = ref(false);
const typed = ref(props.keyword);
const field = ref<HTMLInputElement | null>(null);
const wrap = ref<HTMLElement | null>(null);

/** 地址里的词变了,框里跟着走 —— 收起时它就是那一页在搜什么。 */
watch(
  () => props.keyword,
  (value) => (typed.value = value),
);

/** 最近搜索。存坏了就当没有,不该拦着搜索。 */
const recent = ref<string[]>(readRecent());

function readRecent(): string[] {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(RECENT_KEY) ?? "[]");
    if (!Array.isArray(saved)) return [];
    return saved.filter((item): item is string => typeof item === "string").slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

function remember(word: string) {
  const next = [word, ...recent.value.filter((item) => item !== word)].slice(0, RECENT_MAX);
  recent.value = next;
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // 存不下(隐私模式、配额满)就算了
  }
}

function forgetAll() {
  recent.value = [];
  try {
    localStorage.removeItem(RECENT_KEY);
  } catch {
    // 同上
  }
}

/**
 * 库里最多的标签。**只在第一次展开时取一次**:这份名单变得很慢,而顶栏每点一次搜索都去问一遍,是拿一次请求换一个几乎一样的答案。取不到就空着,不再报错。
 */
const topTags = ref<{ name: string; count: number }[] | null>(null);

async function loadTopTags() {
  if (topTags.value) return;
  try {
    const all = await tags.list();
    const counted = new Map<string, number>();
    for (const tag of all) {
      counted.set(tag.name, (counted.get(tag.name) ?? 0) + tag.edition_count);
    }
    topTags.value = [...counted]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count || a.name.localeCompare(b.name, "zh"))
      .slice(0, TAG_MAX);
  } catch {
    topTags.value = [];
  }
}

function expand() {
  if (expanded.value) return;
  expanded.value = true;
  void loadTopTags();
  void nextTick(() => field.value?.focus());
}

function collapse() {
  if (!expanded.value) return;
  expanded.value = false;
  typed.value = props.keyword; // 收起时回到地址里那一个词,不留下半句没搜过的话
}

/** 回车、点一个词、点一个标签都走这里:记一笔,报给外壳,收起。 */
function submit(word: string = typed.value) {
  const text = word.trim();
  if (text) remember(text);
  typed.value = text;
  collapse();
  emit("search", text);
}

function clearTyped() {
  typed.value = "";
  field.value?.focus();
}

/** 焦点离开这一块就收起;还在里面(比如刚点到面板上的词)不算。 */
function onFocusOut(event: FocusEvent) {
  const next = event.relatedTarget as Node | null;
  if (next && wrap.value?.contains(next)) return;
  collapse();
}

/**
 * 点在这一块的空白处不该把光标从输入框里拿走 —— 拿走就触发上面的「焦点离开了」,刚敲一半的词会跟着收起被抹掉。所以挡掉默认行为;输入框与按钮照常。
 */
function keepFocus(event: MouseEvent) {
  const target = event.target as HTMLElement | null;
  if (target?.closest("input, button")) return;
  event.preventDefault();
}

function onPointerDown(event: PointerEvent) {
  if (!expanded.value) return;
  if (wrap.value && !wrap.value.contains(event.target as Node)) collapse();
}

onMounted(() => document.addEventListener("pointerdown", onPointerDown));
onUnmounted(() => document.removeEventListener("pointerdown", onPointerDown));
</script>

<template>
  <div
    ref="wrap"
    class="static sm:relative"
    @keydown.escape="collapse()"
    @focusout="onFocusOut"
    @mousedown="keepFocus"
  >
    <!--
      收起时就是这一枚放大镜,**它一直都在**(展开时不隐藏)—— 位置占着,顶栏才不会因为展开而挪动;宽屏上它被上面那一层盖住,窄屏上再点一下就是收起。
    -->
    <button
      type="button"
      :aria-expanded="expanded"
      aria-label="搜索"
      title="搜索"
      :class="[
        'inline-flex size-9 shrink-0 items-center justify-center rounded-control border transition-colors',
        expanded
          ? 'border-accent bg-surface text-accent-text'
          : 'border-line text-muted hover:bg-state-hover hover:text-fg active:bg-state-press',
      ]"
      @click="expanded ? collapse() : expand()"
    >
      <svg
        viewBox="0 0 24 24"
        class="size-[18px]"
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linecap="round"
        aria-hidden="true"
      >
        <circle cx="10.8" cy="10.8" r="6.6" />
        <path d="m15.6 15.6 4.6 4.6" />
      </svg>
    </button>

    <!--
      展开的那一层。**它是 absolute,所以不占地方**。窄屏 `inset-x-4 top-full` 挂在卡片下沿、与卡片同宽;宽屏 `sm:right-0 sm:top-0 sm:w-[22rem]` 贴着那一枚图标向左长出来。
    -->
    <div
      v-if="expanded"
      class="absolute inset-x-4 top-full z-(--pn-z-overlay) mt-2 sm:inset-x-auto sm:top-0 sm:right-0 sm:mt-0 sm:w-[22rem] sm:max-w-[calc(100vw-4rem)]"
    >
      <div class="flex h-9 items-center gap-1.5 rounded-control border border-accent bg-surface px-3">
        <svg
          viewBox="0 0 24 24"
          class="size-4 shrink-0 text-muted"
          fill="none"
          stroke="currentColor"
          stroke-width="1.8"
          stroke-linecap="round"
          aria-hidden="true"
        >
          <circle cx="10.8" cy="10.8" r="6.6" />
          <path d="m15.6 15.6 4.6 4.6" />
        </svg>

        <!-- 窄屏 16px、宽屏 15px(--text-base):小于 16px 的输入框在 iOS 上会把整页放大。 -->
        <input
          ref="field"
          v-model="typed"
          type="search"
          placeholder="搜索作品、作者、标签"
          aria-label="搜索作品、作者、标签"
          class="h-full w-full min-w-0 bg-transparent text-[1rem] text-fg outline-none placeholder:text-disabled sm:text-base [&::-webkit-search-cancel-button]:hidden"
          @keydown.enter="submit()"
        />

        <CloseButton v-if="typed" label="清掉" @click.stop="clearTyped" />
      </div>

      <!-- 面板。和外观那个面板一个做法:靠 CSS 定位、没有阴影。**点外面关的判据是 DOM 包含关系**,面板是本组件的子节点,所以它在哪一侧都不影响。 -->
      <div class="mt-2 rounded-card border border-line bg-surface p-3">
        <div v-if="recent.length" class="flex flex-col gap-2">
          <div class="flex items-baseline justify-between">
            <Text size="sm" tone="muted">最近搜索</Text>
            <button
              type="button"
              class="text-sm text-muted transition-colors hover:text-fg"
              @click="forgetAll"
            >
              清除
            </button>
          </div>

          <div class="flex flex-wrap gap-1.5">
            <button
              v-for="word in recent"
              :key="word"
              type="button"
              class="max-w-full truncate rounded-pill border border-line px-2.5 py-1 text-sm transition-colors hover:bg-state-hover active:bg-state-press"
              @click="submit(word)"
            >
              {{ word }}
            </button>
          </div>
        </div>

        <div
          v-if="topTags?.length"
          :class="['flex flex-col gap-0.5', recent.length ? 'mt-3 border-t border-line pt-3' : '']"
        >
          <Text size="sm" tone="muted">库里最多的标签</Text>

          <!-- 一行一个标签:名次用主色,右边跟一个数量 —— 不写数量就只是八个词,看不出凭什么排这个顺序。 -->
          <button
            v-for="(tag, index) in topTags"
            :key="tag.name"
            type="button"
            class="flex items-baseline gap-2.5 rounded-control px-2 py-1 text-left transition-colors hover:bg-state-hover active:bg-state-press"
            @click="submit(tag.name)"
          >
            <span class="w-3 shrink-0 text-right text-sm text-accent-text tabular-nums">
              {{ index + 1 }}
            </span>
            <span class="min-w-0 flex-1 truncate text-base">{{ tag.name }}</span>
            <span class="shrink-0 text-sm text-muted">{{ tag.count }}</span>
          </button>
        </div>

        <Text v-if="topTags && !topTags.length && !recent.length" size="sm" tone="muted">
          这个库里还没有标签。
        </Text>
      </div>
    </div>
  </div>
</template>
