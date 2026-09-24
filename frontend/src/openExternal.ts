import { openUrl } from "@tauri-apps/plugin-opener";

/**
 * 在桌面版交给系统默认浏览器，在普通网页里保持浏览器原本的新标签行为。
 * 这里只允许网页协议，避免把设置页返回的意外字符串交给操作系统处理。
 */
export async function openExternal(rawUrl: string): Promise<void> {
  const url = new URL(rawUrl);
  if (url.protocol !== "https:" && url.protocol !== "http:") {
    throw new Error("只能打开 http 或 https 链接。");
  }

  const desktop = "__TAURI_INTERNALS__" in window;
  if (desktop) {
    await openUrl(url.href);
    return;
  }

  window.open(url.href, "_blank", "noopener,noreferrer");
}
