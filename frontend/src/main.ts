import { createApp } from "vue";

import App from "./App.vue";
import { router } from "./router";
import { loadMediaTypes } from "./mediaTypes";
import { loadSourceNames } from "./sourceNames";
import { watchTheme } from "./theme";
import { watchAccent } from "./colors";
import "./style.css";

// 主题在挂载之前接上:选择一变(或系统偏好一变)就往 <html> 上改那个 dark 类。
watchTheme();

// 主色:自己挑过颜色时按当前主题算出五个值;主题切换时再算一遍(深色下的链接色
// 比浅色下亮,不能拿浅色那一套接着用)。
watchAccent();

// 类型那一条要用它,所以先取回来再挂载:取不到时外壳会显示一句话,而不是画一条空白的条。
await loadMediaTypes();

// 数据源的名字(bangumi → Bangumi)也先取回来:两处「从数据源找」都会画它,
// 取不到时会原样显示短名 —— 那是能跑但不好看的降级,不该等到那时候才发现。
await loadSourceNames();

createApp(App).use(router).mount("#app");
