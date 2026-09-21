/**
 * 数据源的名字:短名(bangumi / vndb)→ 画在页面上的名字,启动时从 `/api/sources` 取一次。
 *
 * 名字不写在代码里:加一个源是「一个模块 + 一处注册」,前端自己抄一份的话,加源时忘了改这里
 * 不会报错,只会把短名画到页面上。取不到就原样显示短名 —— 名字不值得为它拦住整页。
 */

import { ref } from "vue";

import { sources } from "./api";

const labels = ref<Record<string, string>>({});

export async function loadSourceNames(): Promise<void> {
  if (Object.keys(labels.value).length) return;
  try {
    labels.value = Object.fromEntries((await sources.list()).map((item) => [item.name, item.label]));
  } catch {
    // 取不到就原样显示短名:这一句只是画在页面上的一个名字,不该拦住整页。
  }
}

/** 一个源给人看的名字;不认识时原样返回取值。 */
export function labelOfSource(name: string): string {
  return labels.value[name] ?? name;
}
