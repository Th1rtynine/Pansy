/**
 * 全站的明暗主题:浅色、深色、跟随系统三个选择,存在 localStorage 里。做法只有一句话:往 `<html>` 上
 * 加不加 `dark` 这个类(`.dark` 那段在 semantic.css 里,组件一处都不写 `dark:` 变体)。「跟随系统」跟着
 * 系统偏好变,所以挂了监听;首屏那一下由 `index.html` 里抢先跑的一小段上色(等这里加载完深色下会闪白)。
 */
import { computed, ref, watch } from "vue";

export type ThemeChoice = "light" | "dark" | "system";

export const THEME_OPTIONS = [
  { value: "light", label: "浅色" },
  { value: "dark", label: "深色" },
  { value: "system", label: "跟随系统" },
];

const STORAGE_KEY = "pansy.theme";

/** 系统是不是深色。它自己会变(比如日落时系统自动切换),所以要监听。 */
const systemPrefersDark = window.matchMedia("(prefers-color-scheme: dark)");
const systemDark = ref(systemPrefersDark.matches);
systemPrefersDark.addEventListener("change", (event) => {
  systemDark.value = event.matches;
});

function readChoice(): ThemeChoice {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved === "light" || saved === "dark" || saved === "system" ? saved : "system";
}

export const themeChoice = ref<ThemeChoice>(readChoice());

/** 现在到底是不是深色。三个选择收敛成这一个布尔值,别处只问它。 */
export const isDark = computed(
  () => themeChoice.value === "dark" || (themeChoice.value === "system" && systemDark.value),
);

function paint() {
  document.documentElement.classList.toggle("dark", isDark.value);
}

export function chooseTheme(choice: ThemeChoice) {
  themeChoice.value = choice;
  localStorage.setItem(STORAGE_KEY, choice);
}

/** 在 main.ts 里挂载之前调一次;之后选择一变就重画。 */
export function watchTheme() {
  watch(isDark, paint, { immediate: true });
}
