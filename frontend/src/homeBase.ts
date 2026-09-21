/**
 * 「主页就是这个标签页的起始页」—— 点左上角那朵三色堇时用。浏览器没有删历史项的接口,所以先退到本文档第
 * 一格、再把那一格改写成主页(之后的整段成为「前进」);退几格 = 当前 `position` 减首次求值时的
 * `position`;落地那一格不上屏,由 `router.ts` 的守卫改写(见 `takeLanding()`)。
 */

import { NavigationFailureType, isNavigationFailure, type Router } from "vue-router";

import { TOP_LEVEL, forgetTrail } from "./trail";

/**
 * 起步那一格:本文档第一次求值时,当前历史项在标签页里的序号。刚打开的文档 `history.state` 还是空的,
 * 那时按 `history.length - 1` 算 —— 与 vue-router 自己给第一项写的值是同一个式子。
 */
const start: number = (() => {
  const state = window.history.state as { position?: number } | null;
  if (state && typeof state.position === "number") return state.position;
  return window.history.length - 1;
})();

/** 回退正在落地:落到的那一格要改写成主页(守卫取走它)。 */
let landing = false;

/** 现在比起步那一格深了几格。没走过就是 0。 */
export function depthFromStart(): number {
  const state = window.history.state as { position?: number } | null;
  const now = state && typeof state.position === "number" ? state.position : start;
  return Math.max(0, now - start);
}

/**
 * 点站名:先按常规走一次「回主页」,确认没被拦下再截断历史 —— 反过来先 `history.go(-n)`,编辑页的未保存
 * 提醒再拦也退不回去。`router` 由调用方传入(在这里 import 会与 `router.ts` 成环)。
 */
export async function goHomeFromTheLogo(router: Router): Promise<void> {
  const depth = depthFromStart();
  const failure = await router.replace(TOP_LEVEL);
  /**
   * `aborted` / `cancelled` 才算「被拦下」。不能拿「有没有 failure」当判据:已经站在主页上再点一次时
   * 会回一个 `duplicated`,那一次是**要**截断的(人正是想清掉走过的路)。
   */
  if (isNavigationFailure(failure, NavigationFailureType.aborted | NavigationFailureType.cancelled)) {
    return;
  }
  forgetTrail();
  if (depth <= 0) return;
  landing = true;
  window.history.go(-depth);
  /**
   * 兜底:落点与当前页是同一个地址(vue-router 当成重复跳转,直接跳过守卫)或压根没落地时,补一次
   * replace —— 前者正好把起点那一格改写成主页,后者保证「点站名会回主页」不会失效。
   */
  window.setTimeout(() => {
    if (!landing) return;
    landing = false;
    void router.replace(TOP_LEVEL);
  }, 300);
}

/** 守卫用:这一趟是不是「重定位」的落地。取走就没了。 */
export function takeLanding(): boolean {
  if (!landing) return false;
  landing = false;
  return true;
}
