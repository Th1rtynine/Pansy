/**
 * 一次读取的三个状态:数据、错误、正在读 —— 每个页面都要这三样,写法每次都一样,收在这里一处;错误消息
 * 直接取 `ApiError` 里那句中文。`watchSource` 给了就跟着它重读一次(通常是地址);`reload({ silent: true })`
 * 是不亮「正在读」的悄悄取,已经画好的那一屏留在原地等新的换上来。
 */
import { onActivated, ref, watch, type Ref } from "vue";

import { ApiError } from "./api";

export function useLoad<T>(load: () => Promise<T>, watchSource?: () => unknown) {
  const data = ref<T | null>(null) as Ref<T | null>;
  const error = ref("");
  const loading = ref(false);

  async function run(options: { silent?: boolean } = {}) {
    if (!options.silent) loading.value = true;
    error.value = "";
    try {
      data.value = await load();
    } catch (failure) {
      data.value = null;
      error.value = failure instanceof ApiError ? failure.message : String(failure);
    } finally {
      if (!options.silent) loading.value = false;
    }
  }

  if (watchSource) watch(watchSource, () => run(), { immediate: true });
  else void run();

  return { data, error, loading, reload: run };
}

/**
 * 被 KeepAlive 缓存的页面回到眼前时再悄悄取一次。第一次激活紧跟着挂载(那时已经取过一遍),
 * 所以跳过那一次;取的时候不亮「正在读」,那一屏不会塌下去,滚动位置也回得去。
 */
export function useReloadOnReturn(reload: () => void) {
  let mounted = false;
  onActivated(() => {
    if (!mounted) {
      mounted = true;
      return;
    }
    reload();
  });
}

/** 把一次写入的失败变成一句话,写法与 useLoad 一致。 */
export function messageOf(failure: unknown): string {
  return failure instanceof ApiError ? failure.message : String(failure);
}
