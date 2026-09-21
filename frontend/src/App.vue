<script setup lang="ts">
/**
 * 全站的外壳:顶栏(站名 + 四个类型 + 搜索 + 外观/加入作品)与下面被换掉的内容。顶栏在每一页上都要有,所以在这里;
 * 「全部」不是条目,归站名管(类型都不亮就是 `/works` 不带 `media_type`);选中的类型与搜索词都从地址读,当前所在用 `--pn-mark` 标出。
 * 顶栏与手机底部导航(768px 起反过来)谁露面由 CSS 决定;每一格带一圈 2px 透明边框,亮起来的那一格才不会撑大整排。
 */
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink, RouterView, useRoute, useRouter } from "vue-router";
import { Alert, Container, Text } from "./ui";

import BackToPrevious from "./components/BackToPrevious.vue";
import BackToTop from "./components/BackToTop.vue";
import BrandLogo from "./components/BrandLogo.vue";
import HeaderSearch from "./components/HeaderSearch.vue";
import HomeIcon from "./components/HomeIcon.vue";
import MediaTypeIcon from "./components/MediaTypeIcon.vue";
import MobileTabBar from "./components/MobileTabBar.vue";
import { ACCENT_PRESETS, accentChoice, chooseAccent } from "./colors";
import { goHomeFromTheLogo } from "./homeBase";
import { loadFailure, mediaTypes } from "./mediaTypes";
import { THEME_OPTIONS, chooseTheme, themeChoice, type ThemeChoice } from "./theme";

const route = useRoute();
const router = useRouter();

/**
 * 哪几页留在内存里(KeepAlive 的名单)。三个名字同时写在各自的 `defineOptions` 里,改了要
 * 一起改 —— 对不上时不会报错,只是缓存悄悄不生效。
 */
const KEPT_ALIVE = ["WorksList", "CreatorsList", "TagsList"];

const mediaType = computed(() => (route.query.media_type as string) ?? "");

/** 四个条目:就是四个类型。 */
const items = computed(() =>
  mediaTypes.value.map((item) => ({ value: item.value, label: item.label })),
);

/** 当前在哪一条上。**只在列表页算数** —— 打开一条记录时地址里没有类型,那时不该有任何一个条目亮着。 */
const currentType = computed(() => (route.path === "/works" ? mediaType.value : null));

/**
 * 是不是「全部」那一页:在列表页、且没有选任何一类。导航里那个「主页」条目就代表这一页,所以它带
 * `aria-current="page"`;站名不带 —— 站名不在导航那一排里。
 */
const onAllWorks = computed(() => route.path === "/works" && mediaType.value === "");

/**
 * 是不是「正在加东西 / 正在改东西」的那一页(看 router.ts 里那几个 `meta: TASK`)。那几页上把浏览用的
 * 入口收起来(类型导航、底部导航、站内搜索、加号),它们会把人带离正在填写的内容;站名与外观保留。
 */
const taskPage = computed(() => route.meta.task === true);

function goTo(value: string) {
  // 换一类就回到列表页:类型变了,接着看上一个类型的第几页没有意义。
  router.push({ path: "/works", query: value ? { media_type: value } : {} });
}

/** 搜索框里显示什么:就是地址里的那个词 —— 所以搜过之后刷新、后退,框里还是它。 */
const searchKeyword = computed(() => (route.query.q as string) ?? "");

/**
 * 顶栏里搜了一下。**在列表页里搜,就在当前这一类里搜**(类型与排序留着);**在别的页面上搜,回列表页
 * 搜全部**。页码一定丢掉:换了词,接着看上一个词的第几页没有意义。
 */
function searchFromHeader(text: string) {
  const keyword = text.trim();
  const query: Record<string, string> = {};
  if (route.path === "/works") {
    if (mediaType.value) query.media_type = mediaType.value;
    if (route.query.sort) query.sort = String(route.query.sort);
  }
  if (keyword) query.q = keyword;
  router.push({ path: "/works", query });
}

/**
 * 点左上角那朵三色堇:回主页,并把主页变成这一趟的起点(机制见 `src/homeBase.ts`)。只接普通左键并
 * `preventDefault`:Ctrl/Cmd/Shift/中键是「在新标签页打开」,`href` 那一次真页面加载不能发生。
 */
function onLogoClick(event: MouseEvent) {
  if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
  event.preventDefault();
  goHomeFromTheLogo(router);
}

/** 「恢复默认」:明暗回到跟随系统,主色回到默认那一个。两样都是默认时它不出现。 */
const canReset = computed(() => accentChoice.value !== null || themeChoice.value !== "system");

function resetAppearance() {
  chooseTheme("system");
  chooseAccent(null);
}

/**
 * 哪一块浮层开着:`""`(关着)或 `"appearance"`(外观)。下面那套「点外面关、按 Esc 关」的监听
 * 就为它一块服务,所以这里是「开哪一块」而不是一个布尔 —— 以后再加浮层时不必另写一套。
 */
const openPanel = ref<"" | "appearance">("");
const appearanceWrap = ref<HTMLElement | null>(null);
const appearanceButton = ref<HTMLElement | null>(null);

function togglePanel(which: "appearance") {
  openPanel.value = openPanel.value === which ? "" : which;
}

function onPointerDown(event: PointerEvent) {
  if (!openPanel.value) return;
  const wrap = appearanceWrap.value;
  if (wrap && !wrap.contains(event.target as Node)) {
    openPanel.value = "";
  }
}

function onKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape" || !openPanel.value) return;
  openPanel.value = "";
  // 焦点回到那枚按钮,不然键盘用户会掉在原地
  appearanceButton.value?.focus();
}

onMounted(() => {
  document.addEventListener("pointerdown", onPointerDown);
  document.addEventListener("keydown", onKeydown);
});

onUnmounted(() => {
  document.removeEventListener("pointerdown", onPointerDown);
  document.removeEventListener("keydown", onKeydown);
});
</script>

<template>
  <div class="flex min-h-screen flex-col bg-canvas text-fg">
    <!-- 顶栏是一张轻薄的长卡片。正文仍保持适合阅读的宽度,顶栏单独放宽以容纳导航与搜索。 -->
    <header class="z-(--pn-z-overlay) px-1 pt-2 md:sticky md:top-0">
      <Container size="header">
        <div
          class="site-header relative flex flex-wrap items-center gap-x-4 gap-y-2 rounded-card border border-line bg-surface/90 px-4 py-2.5 backdrop-blur-xl xl:flex-nowrap"
        >
          <!--
            站名是花体的落款,不再承担 `aria-current` ——「回到首页」明写在旁边那个「主页」条目上,两个东西同时说「你在这里」只会让人分不清。
            这里用真的 `<a href>` 而不是 `RouterLink`:后者自己那一跳会先跑掉,再重定位就成了两次跳转;`href` 留着,Ctrl/中键点仍由浏览器管。
          -->
          <a
            href="/works"
            aria-label="Pansy 主页"
            title="回到首页"
            class="shrink-0 rounded-control text-accent-text transition-opacity hover:opacity-(--pn-fade-hover-opacity)"
            @click="onLogoClick"
          >
            <BrandLogo />
          </a>

          <!--
            四个类型(加「主页」)直接落在顶栏卡片里,窗口较窄时这一行可以横向滚动。**手机上这一条不出现**
            (`hidden md:block`),那个宽度下换成底部那一条(见 components/MobileTabBar.vue),谁露面由 CSS 决定。
          -->
          <nav
            :class="[
              'min-w-0 overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden',
              taskPage ? 'hidden' : 'hidden md:block',
            ]"
          >
            <!-- `w-max` 让导航自身不换行;空间不足时由外层横向滚动。 -->
            <div class="flex w-max items-center gap-0.5">
              <!-- 主页:一条直的链接(地址是固定的),当前那一条用鼠尾草绿整圈边框标出来 -->
              <RouterLink
                to="/works"
                :aria-current="onAllWorks ? 'page' : undefined"
                :class="[
                  'inline-flex items-center gap-1.5 rounded-pill border-2 px-2 py-0.5 text-base transition-colors',
                  onAllWorks
                    ? 'border-mark font-medium text-mark-text'
                    : 'border-transparent text-muted hover:bg-state-hover hover:text-fg',
                ]"
              >
                <HomeIcon />
                主页
              </RouterLink>

              <button
                v-for="item in items"
                :key="item.value"
                type="button"
                :aria-current="currentType === item.value ? 'page' : undefined"
                :class="[
                  'inline-flex items-center gap-1.5 rounded-pill border-2 px-2 py-0.5 text-base transition-colors',
                  currentType === item.value
                    ? 'border-mark font-medium text-mark-text'
                    : 'border-transparent text-muted hover:bg-state-hover hover:text-fg',
                ]"
                @click="goTo(item.value)"
              >
                <MediaTypeIcon :value="item.value" />
                {{ item.label }}
              </button>
            </div>
          </nav>

          <!--
            右边这一组:768px 以下撑满剩下的地方(`flex-1 min-w-0`),768px 起交回自动宽度由 `ms-auto` 顶到右边。撑满是为了让搜索框吃掉剩下的宽度,
            **但里面必须自己靠右**(`justify-end`):搜索改成「收起时就是一枚放大镜」之后它不再长大,没人顶了,图标会停在盒子左边、右边空出一大块。
          -->
          <div class="ms-auto flex min-w-0 flex-1 items-center justify-end gap-2 md:flex-none">
            <HeaderSearch
              v-if="!taskPage"
              :keyword="searchKeyword"
              @search="searchFromHeader"
            />

            <!--
              外观:平时只有一个图标,明暗与主色都收在点开的那面板里。面板靠 CSS 定位(`absolute right-0 top-full`)挂在按钮下面,
              不用 JS 量坐标 —— 浏览器的 `popover` 要在打开那一刻量一次位置,实测摆到过别处;代价是「点外面关、按 Esc 关」要自己写。
            -->
            <div ref="appearanceWrap" class="relative">
              <button
                ref="appearanceButton"
                type="button"
                :aria-expanded="openPanel === 'appearance'"
                aria-controls="appearance"
                aria-label="外观:明暗与主色"
                title="外观"
                class="inline-flex size-9 shrink-0 items-center justify-center rounded-control border border-line text-muted transition-colors hover:bg-state-hover hover:text-fg active:bg-state-press"
                @click="togglePanel('appearance')"
              >
                <svg
                  viewBox="0 0 24 24"
                  class="size-[18px]"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="1.6"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                  aria-hidden="true"
                >
                  <path
                    d="M12 3.2a8.8 8.8 0 1 0 0 17.6c1.1 0 1.9-.8 1.9-1.7 0-.5-.2-.9-.5-1.2-.3-.3-.5-.7-.5-1.1 0-.9.8-1.7 1.8-1.7h1.1a4.9 4.9 0 0 0 4.9-4.9c0-3.9-3.9-7-8.7-7Z"
                  />
                  <circle cx="8.2" cy="10.4" r="1.15" fill="currentColor" stroke="none" />
                  <circle cx="11.8" cy="7.6" r="1.15" fill="currentColor" stroke="none" />
                  <circle cx="15.6" cy="10.2" r="1.15" fill="currentColor" stroke="none" />
                </svg>
              </button>

              <!--
                面板。**没有阴影**:浮层靠 1px 的线与面分开。**主色直接铺成一盘**(六个色块),不再藏在一个圆点后面 —— 挑色这一步不该多点一次。
              -->
              <div
                v-if="openPanel === 'appearance'"
                id="appearance"
                class="absolute right-0 top-full z-(--pn-z-overlay) mt-2 w-56 rounded-card border border-line bg-surface p-3"
              >
                <div class="flex flex-col gap-3">
                  <div class="flex flex-col gap-1.5">
                    <Text size="sm" tone="muted">明暗</Text>

                    <!--
                      **竖排三行,一行一枚图标**:一行比三段控件好认 —— 眼睛扫下去的是一列;当前那一行整行高亮。
                    -->
                    <div class="flex flex-col gap-0.5">
                      <button
                        v-for="option in THEME_OPTIONS"
                        :key="option.value"
                        type="button"
                        :aria-pressed="themeChoice === option.value"
                        :class="[
                          'flex items-center gap-2.5 rounded-control px-2 py-1.5 text-left transition-colors',
                          themeChoice === option.value
                            ? 'bg-accent-soft font-medium text-accent-text'
                            : 'text-fg hover:bg-state-hover active:bg-state-press',
                        ]"
                        @click="chooseTheme(option.value as ThemeChoice)"
                      >
                        <!-- 亮色:太阳 -->
                        <svg
                          v-if="option.value === 'light'"
                          viewBox="0 0 24 24"
                          class="size-4 shrink-0"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.7"
                          stroke-linecap="round"
                          aria-hidden="true"
                        >
                          <circle cx="12" cy="12" r="4" />
                          <path
                            d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M18.4 5.6 17 7M7 17l-1.4 1.4"
                          />
                        </svg>

                        <!-- 深色:月亮 -->
                        <svg
                          v-else-if="option.value === 'dark'"
                          viewBox="0 0 24 24"
                          class="size-4 shrink-0"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.7"
                          stroke-linecap="round"
                          stroke-linejoin="round"
                          aria-hidden="true"
                        >
                          <path d="M20 14.4A8.2 8.2 0 0 1 9.6 4 8.4 8.4 0 1 0 20 14.4Z" />
                        </svg>

                        <!-- 跟随系统:一半亮一半暗的圆 -->
                        <svg
                          v-else
                          viewBox="0 0 24 24"
                          class="size-4 shrink-0"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="1.7"
                          aria-hidden="true"
                        >
                          <circle cx="12" cy="12" r="8" />
                          <path d="M12 4a8 8 0 0 1 0 16Z" fill="currentColor" stroke="none" />
                        </svg>

                        {{ option.label }}
                      </button>
                    </div>

                    <!-- 「恢复默认」摆在明暗这一块的右下角:明暗回到跟随系统,主色回到默认那一个 -->
                    <div v-if="canReset" class="flex justify-end">
                      <button
                        type="button"
                        title="明暗回到跟随系统,主色回到默认那一个"
                        class="text-sm text-muted transition-colors hover:text-fg"
                        @click="resetAppearance"
                      >
                        ⟲ 恢复默认
                      </button>
                    </div>
                  </div>

                  <div class="flex flex-col gap-2">
                    <Text size="sm" tone="muted">主色</Text>
                    <div class="grid grid-cols-6 gap-1.5" role="group" aria-label="主色">
                      <button
                        v-for="preset in ACCENT_PRESETS"
                        :key="preset.hex"
                        type="button"
                        :title="preset.name"
                        :aria-label="preset.name"
                        :aria-pressed="accentChoice === preset.hex"
                        class="size-6 rounded-full border transition-transform hover:scale-110"
                        :class="
                          accentChoice === preset.hex ? 'border-2 border-accent-text' : 'border-line'
                        "
                        :style="{ backgroundColor: preset.hex }"
                        @click="chooseAccent(preset.hex)"
                      ></button>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <!--
              加入作品那一格:直通加入页,不再收在窗格后面 —— 谁打开都能加、能改,顶栏右边就三枚一样大的图标
              (搜索、外观、加号)。**加 / 改的页面上也照常摆出来**:不摆的话进了编辑页右上角什么都没有,只能猜自己是不是跑错了地方。
            -->
            <RouterLink
              to="/works/new"
              aria-label="加入作品"
              title="加入作品"
              class="inline-flex size-9 shrink-0 items-center justify-center rounded-control border border-line text-muted transition-colors hover:bg-state-hover hover:text-fg active:bg-state-press"
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
                <path d="M12 5.5v13M5.5 12h13" />
              </svg>
            </RouterLink>
          </div>
        </div>
      </Container>
    </header>

    <!--
      正文这一列。**手机上底下多留一块**(`pb-24`,96px):底部导航是 `fixed`,不留的话最后一行会被它压住 —— 96px = 那一条 59px + iPhone 底下横杠最多 34px。宽屏上没有那一条,回到 `md:pb-6`。
    -->
    <main class="flex-1 pt-6 pb-24 md:pb-6">
      <Container size="shell" class="flex flex-col gap-5">
        <Alert v-if="loadFailure" tone="danger" title="读不到类型表">
          {{ loadFailure }} —— 后端没起来,或者 /api 没有转过去(见 vite.config.ts)。
        </Alert>

        <!--
          三个列表页**留在内存里**:不留的话退回来会重新请求一遍,页面先塌成「正在读取」,滚动位置也没得回。回来时**先原样显示,再悄悄取一次新的**
          (见 useLoad.ts 的 useReloadOnReturn),留住的是版式与位置。**只留列表,不留表单与详情** —— 表单留着会带回上一次填的东西,那是错;名单要与 `defineOptions` 对得上。
        -->
        <RouterView v-slot="{ Component }">
          <KeepAlive :include="KEPT_ALIVE">
            <component :is="Component" />
          </KeepAlive>
        </RouterView>
      </Container>
    </main>


    <!-- 右下角那两枚:**「回到上一页」在上面,「回到顶部」在下面**(见各自的文件) -->
    <BackToPrevious />
    <BackToTop />

    <!--
      手机上那一条**底部导航**(见 components/MobileTabBar.vue):顶栏那一排在 768px 以下由它接手,主页居中,两边各两个类型;宽屏上整条不显示(`md:hidden`)。
    -->
    <MobileTabBar
      v-if="!taskPage"
      :items="items"
      :current="currentType"
      :on-home="onAllWorks"
      @pick="goTo"
    />
  </div>
</template>

<style scoped>
.site-header {
  box-shadow: var(--pn-header-shadow);
}
</style>
