/**
 * 走过的页面 —— 右下角那枚「回到上一页」按钮要用。
 * 规则:上一页指上一个页面。浏览器不给历史,所以自己记一份走过的完整地址
 * (最近的在最后);刷新后为空也退回最上级,连着一样的不记两条,
 * `takePrevious` 取走即删,所以按两次退两步。
 */

import { ref } from "vue";

/** 最上级:没有上一页时去那里(`/` 会转到它)。 */
export const TOP_LEVEL = "/works";

/** 最多记这么多格,只留最近的。 */
const MOST = 30;

const trail = ref<string[]>([]);

/**
 * 这一趟是不是按钮自己走的。按「上一页」本身也是一次跳转,不挡的话第二下会弹回原页,
 * 在两页之间来回。
 */
let cameFromTheButton = false;

/** 从某一页离开时记一笔。 */
export function rememberLeaving(fullPath: string): void {
  if (cameFromTheButton) {
    cameFromTheButton = false;
    return;
  }
  if (!fullPath) return;
  if (trail.value[trail.value.length - 1] === fullPath) return;
  trail.value.push(fullPath);
  if (trail.value.length > MOST) trail.value.shift();
}

/**
 * 上一页的地址;没有(或取出来的就是当前这一页)就回最上级。**取走**它。
 * 与当前页相同的一律跳过;退回最上级那一次也要把「按钮走的」记上。
 */
export function takePrevious(current: string): string {
  cameFromTheButton = true;
  while (trail.value.length) {
    const last = trail.value.pop() as string;
    if (last !== current) return last;
  }
  return TOP_LEVEL;
}

/** 现在记着几格。 */
export function trailLength(): number {
  return trail.value.length;
}

/**
 * 清空记录,并且压住这一趟的「离开」(点站名重定位到主页时用,见 `src/homeBase.ts`)。
 * 不压的话,重定位那一趟退到起点时会被记成「上一页」,按钮又把人送回深层页。
 */
export function forgetTrail(): void {
  trail.value = [];
  cameFromTheButton = true;
}
