/**
 * 四个媒体类型与它们各自的字段名,启动时从 `/api/media-types` 取一次。**那张表不在前端**:「哪个类型
 * 记哪几项、每项叫什么」在后端 `app/fields.py` 的 `MEDIA_TYPE_FIELDS`,前端抄一份迟早会过期。
 * `fieldsOf()` / `labelOf()` 是取它的两个入口;模块级的一个 ref 而不是 provide/inject,这一层只需要一份。
 */

import { ref } from "vue";

import { meta } from "./api";
import type { MediaTypeOut } from "./types";

export const mediaTypes = ref<MediaTypeOut[]>([]);
/** 取不到时留下的那句话,由外壳显示出来 —— 取不到时整页都没法用。 */
export const loadFailure = ref("");

export async function loadMediaTypes(): Promise<void> {
  if (mediaTypes.value.length) return;
  try {
    mediaTypes.value = (await meta.mediaTypes()).items;
  } catch (failure) {
    loadFailure.value = failure instanceof Error ? failure.message : String(failure);
  }
}

/** 一个类型的字段名表;不认识的类型给一份空的,调用方不必到处判空。 */
export function fieldsOf(mediaType: string): Record<string, string> {
  return mediaTypes.value.find((item) => item.value === mediaType)?.fields ?? {};
}

/** 一个类型给人看的名字;不认识时原样返回取值。 */
export function labelOf(mediaType: string): string {
  return mediaTypes.value.find((item) => item.value === mediaType)?.label ?? mediaType;
}
