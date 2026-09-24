import { createRouter, createWebHistory } from "vue-router";

import { takeLanding } from "./homeBase";
import { TOP_LEVEL, rememberLeaving } from "./trail";

/** 地址与页面的对应表。**地址就是状态**:搜什么、看哪一类、第几页、按什么排全在地址里,翻页与筛选就是改地址。 */
/** `meta: task` 的那几页(见 App.vue 的 `taskPage`):浏览用的入口都收起来,它们会把人带离正在填写的内容。 */
const TASK = { task: true };

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", redirect: "/works" },

    { path: "/works", name: "works", component: () => import("./pages/WorksList.vue") },
    // 加入作品:一张页面走完「选类型 → 从源预填 → 自己改 → 保存」。
    {
      path: "/works/new",
      name: "work-new",
      meta: TASK,
      component: () => import("./pages/AddWork.vue"),
    },
    { path: "/works/:id", name: "work", component: () => import("./pages/WorkDetail.vue") },
    { path: "/works/:id/edit", name: "work-edit", meta: TASK, component: () => import("./pages/WorkForm.vue") },
    {
      path: "/works/:workId/editions/new",
      name: "edition-new",
      meta: TASK,
      component: () => import("./pages/CarrierForm.vue"),
    },

    { path: "/editions/:id", name: "edition", component: () => import("./pages/CarrierDetail.vue") },
    {
      path: "/editions/:id/edit",
      name: "edition-edit",
      meta: TASK,
      component: () => import("./pages/CarrierForm.vue"),
    },

    { path: "/volumes/:id", name: "volume", component: () => import("./pages/VolumeDetail.vue") },
    {
      path: "/volumes/:id/edit",
      name: "volume-edit",
      meta: TASK,
      /**
       * **这一页本身没有界面**:改一卷就在它所属那一件的页面上(点卷卡就地展开)。旧地址与书签照旧能用,
       * 换成那一件的编辑页并把这一卷带在 `?volume=` 里,父页读到就展开它;`replace` 免得历史多一格。
       */
      beforeEnter: async (to) => {
        const { volumes } = await import("./api");
        const volume = await volumes.get(Number(to.params.id));
        return {
          path: `/editions/${volume.edition_id}/edit`,
          query: { volume: String(volume.id) },
          replace: true,
        };
      },
      component: () => import("./pages/VolumeForm.vue"),
    },

    {
      path: "/creators",
      name: "creators",
      component: () => import("./pages/CreatorsList.vue"),
    },
    {
      path: "/creators/:id",
      name: "creator",
      component: () => import("./pages/CreatorDetail.vue"),
    },
    {
      path: "/creators/:id/edit",
      name: "creator-edit",
      meta: TASK,
      component: () => import("./pages/CreatorForm.vue"),
    },

    { path: "/tags", name: "tags", component: () => import("./pages/TagsList.vue") },
    { path: "/tags/:id", name: "tag", component: () => import("./pages/TagDetail.vue") },
    { path: "/tags/:id/edit", name: "tag-edit", meta: TASK, component: () => import("./pages/TagForm.vue") },

    /**
     * 设置:外部数据源的凭据与账号连接。**不是 `meta: TASK`** ——
     * 它不是一个「填写中」的表单,而是一页要跟别处并排看的配置,浏览用的入口不必收起来。
     */
    { path: "/settings", name: "settings", component: () => import("./pages/Settings.vue") },

    {
      path: "/:rest(.*)*",
      name: "missing",
      component: () => import("./pages/NotFound.vue"),
    },
  ],
  // 后退与前进**回到原来的位置**,别的跳转从顶部开始(浏览器只在后退/前进时给 `savedPosition`)。
  scrollBehavior: (_to, _from, savedPosition) => savedPosition ?? { top: 0 },
});

/**
 * 进门那一下的两件小事:**把结尾多一条斜杠的地址扶正**、**把点站名时留下的落点改写成主页**。
 * 「加东西 / 改东西」的那几页(`meta: TASK`)照旧直接进得去(见 App.vue 的 `taskPage`)。
 */
router.beforeEach((to) => {
  /**
   * **结尾多一条斜杠的地址先扶正。** `/works/` 与 `/works` 是同一页,但 `route.path` 还是原始那串,而界面判「现在在哪一条上」
   * 用的是 `route.path === "/works"`(见 App.vue)—— 不扶正就顶栏不亮。堵在入口而不是改软那 5 处比较;`replace` 免得历史多一格。
   */
  if (to.path.length > 1 && to.path.endsWith("/")) {
    return {
      path: to.path.replace(/\/+$/, "") || "/",
      query: to.query,
      hash: to.hash,
      replace: true,
    };
  }

  /**
   * **点站名那一下的落地**:把落点那一格改写成主页,落点那一页不上屏(机制见 `src/homeBase.ts`)。
   * 放在扶正之后:落点可能是个要重定位的地址,重定位优先。
   */
  if (takeLanding()) return { path: TOP_LEVEL, replace: true };
  return true;
});

/**
 * **记下「刚从哪一页离开」** —— 右下角那枚「回到上一页」要用(见 `src/trail.ts`)。`from.matched.length` 挡的是**第一次进入站点**:
 * 那时 vue-router 给的 `from` 是个空白的起始位置,不挡就会被当成「上一页」记下来,记录里多一格假的。
 */
router.afterEach((_to, from) => {
  if (from.matched.length) rememberLeaving(from.fullPath);
});
