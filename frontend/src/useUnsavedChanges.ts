/**
 * 表单离开保护。
 *
 * 站内跳转用可取消的确认框；刷新、关页与输入新地址交给浏览器自己的提示。
 * 调用方保存成功后应先更新自己的基线，再执行跳转。
 */
import { onBeforeUnmount, onMounted, type Ref } from "vue";
import { onBeforeRouteLeave } from "vue-router";

const DEFAULT_MESSAGE = "还有未保存的修改，确定离开吗？";

export function useUnsavedChanges(
  dirty: Readonly<Ref<boolean>>,
  message = DEFAULT_MESSAGE,
) {
  onBeforeRouteLeave(() => {
    if (!dirty.value) return true;
    return window.confirm(message);
  });

  function beforeUnload(event: BeforeUnloadEvent) {
    if (!dirty.value) return;
    event.preventDefault();
    event.returnValue = "";
  }

  onMounted(() => window.addEventListener("beforeunload", beforeUnload));
  onBeforeUnmount(() => window.removeEventListener("beforeunload", beforeUnload));
}
