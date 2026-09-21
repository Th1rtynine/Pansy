/**
 * 主色可以由使用者自己调。挑一个颜色只给了「实心底」那一处,压在实心底上的字、链接色、浅底与焦点圈
 * 都要从它算出来 —— 算法不同结果就不同(很亮的黄上白字读不清,压在底上的字就该转深色)。
 * 三条规矩:实心底上的字由对比度决定,不写死白或黑(`pickOn`);链接色要自己够重(浅色主题往深里调到 7:1,
 * 深色主题反过来往亮里调);浅底是主色兑内容面(浅色 12%、深色 22%)。深浅两个主题各算一遍(见 `watchAccent`)。
 */
import { ref, watch } from "vue";

import { isDark } from "./theme";

export type AccentPreset = { name: string; hex: string };

/** 六个预设围绕三色堇紫展开;暖金只给 Logo 花心、鼠尾草绿只标记当前位置,不混进主色选择。 */
export const ACCENT_PRESETS: AccentPreset[] = [
  { name: "三色堇紫", hex: "#8559a7" },
  { name: "雾藤紫", hex: "#9d72b8" },
  { name: "深藤紫", hex: "#704e91" },
  { name: "暮蓝紫", hex: "#67669d" },
  { name: "石南紫", hex: "#a05f84" },
  { name: "花瓣紫", hex: "#b68bd0" },
];

export const DEFAULT_ACCENT = ACCENT_PRESETS[0].hex;

const STORAGE_KEY = "pansy.accent";

/** 两个主题的内容面与「实心底上的深色字」;必须和 semantic.css 里那几行一致(这里是第二份副本,算对比度时不必问浏览器)。 */
const LIGHT_SURFACE = "#fffdf9";
const DARK_SURFACE = "#211b27";
const INK_ON_FILL = "#241a2a";

/* ── 颜色计算:都是纯函数,不碰界面 ────────────────────────────────── */

type Rgb = [number, number, number];

function toRgb(hex: string): Rgb {
  const clean = hex.replace("#", "");
  const full =
    clean.length === 3
      ? clean
          .split("")
          .map((c) => c + c)
          .join("")
      : clean;
  return [
    parseInt(full.slice(0, 2), 16),
    parseInt(full.slice(2, 4), 16),
    parseInt(full.slice(4, 6), 16),
  ];
}

function toHex([r, g, b]: Rgb): string {
  const part = (value: number) =>
    Math.max(0, Math.min(255, Math.round(value)))
      .toString(16)
      .padStart(2, "0");
  return `#${part(r)}${part(g)}${part(b)}`;
}

function channelToLinear(value: number): number {
  const c = value / 255;
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
}

/** WCAG 的相对亮度。对比度就是两个亮度算出来的,不是看着估的。 */
function luminance(hex: string): number {
  const [r, g, b] = toRgb(hex);
  return (
    0.2126 * channelToLinear(r) + 0.7152 * channelToLinear(g) + 0.0722 * channelToLinear(b)
  );
}

export function contrast(a: string, b: string): number {
  const [light, dark] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (light + 0.05) / (dark + 0.05);
}

/** 两个颜色按比例兑在一起。weight 是第二个颜色占多少(0 到 1)。 */
function mix(a: string, b: string, weight: number): string {
  const [r1, g1, b1] = toRgb(a);
  const [r2, g2, b2] = toRgb(b);
  return toHex([
    r1 * (1 - weight) + r2 * weight,
    g1 * (1 - weight) + g2 * weight,
    b1 * (1 - weight) + b2 * weight,
  ]);
}

function toHsl(hex: string): { h: number; s: number; l: number } {
  const [r, g, b] = toRgb(hex).map((v) => v / 255) as Rgb;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  const d = max - min;
  if (d === 0) return { h: 0, s: 0, l };
  const s = d / (1 - Math.abs(2 * l - 1));
  let h: number;
  if (max === r) h = 60 * (((g - b) / d) % 6);
  else if (max === g) h = 60 * ((b - r) / d + 2);
  else h = 60 * ((r - g) / d + 4);
  return { h: (h + 360) % 360, s, l };
}

function fromHsl(h: number, s: number, l: number): string {
  const c = (1 - Math.abs(2 * l - 1)) * s;
  const x = c * (1 - Math.abs(((h / 60) % 2) - 1));
  const m = l - c / 2;
  const sector = Math.floor(h / 60) % 6;
  const table: [number, number, number][] = [
    [c, x, 0],
    [x, c, 0],
    [0, c, x],
    [0, x, c],
    [x, 0, c],
    [c, 0, x],
  ];
  const [r, g, b] = table[sector];
  return toHex([(r + m) * 255, (g + m) * 255, (b + m) * 255]);
}

function shiftLightness(hex: string, amount: number): string {
  const { h, s, l } = toHsl(hex);
  return fromHsl(h, s, Math.max(0, Math.min(1, l + amount)));
}

/** 把颜色朝着「离底色更远」的方向调,直到对比度够;底色浅就往深里调,色相与饱和度不动,只动明度。 */
function ensureContrast(color: string, surface: string, target: number): string {
  if (contrast(color, surface) >= target) return color;
  const { h, s, l } = toHsl(color);
  const goDarker = luminance(surface) > 0.5;
  for (let step = 1; step <= 50; step += 1) {
    const next = goDarker ? l - step * 0.02 : l + step * 0.02;
    if (next < 0 || next > 1) break;
    const candidate = fromHsl(h, s, next);
    if (contrast(candidate, surface) >= target) return candidate;
  }
  return goDarker ? "#000000" : "#ffffff";
}

/** 压在实心底上的字:白与深色哪个更清楚就用哪个。 */
function pickOn(fill: string): string {
  return contrast(fill, "#ffffff") >= contrast(fill, INK_ON_FILL) ? "#ffffff" : INK_ON_FILL;
}

/** 从一个颜色算出这个主题下要用的五个值。 */
export function rolesFor(base: string, dark: boolean) {
  const surface = dark ? DARK_SURFACE : LIGHT_SURFACE;
  // 深色主题下先把它提到「压在深底上看得见」的程度,再往下算其余几个。
  const accent = dark ? ensureContrast(base, surface, 4.5) : base;
  return {
    accent,
    accentHover: shiftLightness(accent, dark ? 0.05 : -0.05),
    accentPress: shiftLightness(accent, dark ? -0.04 : -0.09),
    accentOn: pickOn(accent),
    accentText: ensureContrast(accent, surface, 7),
    accentSoft: mix(accent, surface, dark ? 0.22 : 0.12),
    focusRing: accent,
  };
}

/* ── 状态与应用 ──────────────────────────────────────────────────── */

function readChoice(): string | null {
  const saved = localStorage.getItem(STORAGE_KEY);
  return saved && /^#[0-9a-fA-F]{6}$/.test(saved) ? saved : null;
}

/** 挑的颜色。null 表示用样式表里的默认主色。 */
export const accentChoice = ref<string | null>(readChoice());

const OVERRIDDEN = [
  "--pn-accent",
  "--pn-accent-hover",
  "--pn-accent-press",
  "--pn-accent-on",
  "--pn-accent-text",
  "--pn-accent-soft",
  "--pn-focus-ring",
] as const;

/**
 * 把当前主题下该用的值写到 `<html>` 的行内样式上。写行内是因为它优先级高于任何选择器,能同时压过 `:root` 与 `.dark` 里那几行;代价是主题一切换就得重算。
 */
export function applyAccent(dark: boolean) {
  const style = document.documentElement.style;
  const base = accentChoice.value;
  if (!base) {
    for (const name of OVERRIDDEN) style.removeProperty(name);
    return;
  }
  const roles = rolesFor(base, dark);
  style.setProperty("--pn-accent", roles.accent);
  style.setProperty("--pn-accent-hover", roles.accentHover);
  style.setProperty("--pn-accent-press", roles.accentPress);
  style.setProperty("--pn-accent-on", roles.accentOn);
  style.setProperty("--pn-accent-text", roles.accentText);
  style.setProperty("--pn-accent-soft", roles.accentSoft);
  style.setProperty("--pn-focus-ring", roles.focusRing);
}

export function chooseAccent(hex: string | null) {
  accentChoice.value = hex;
  if (hex) localStorage.setItem(STORAGE_KEY, hex);
  else localStorage.removeItem(STORAGE_KEY);
}

/** 在 main.ts 里调一次;挑颜色本身也要重画,所以连 accentChoice 一起监视。 */
export function watchAccent() {
  watch([isDark, accentChoice], () => applyAccent(isDark.value), { immediate: true });
}
