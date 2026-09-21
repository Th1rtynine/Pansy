/**
 * 把一串「逐字段建议」落到一张表单上,「加入作品」与作品编辑页共用这一段,所以规矩只有一份:默认只填
 * 空格子(要盖掉已经写好的字得明说,见 `overwrite`);简介优先中文那一份;列表类字段有上限(作者 12 位、
 * 标签 12 个、别名 8 条),没填进去多少如实说(返回值里的 `skippedTags`);不写库、不改地址。
 */
import type { EditionIn, SourceSuggestion, WorkIn } from "./types";

/** 一屏里放得下的条数:作者、标签、别名各一个上限。 */
export const TAG_TAKE = 12;
export const CREATOR_TAKE = 12;
export const ALIAS_TAKE = 8;

export type PrefillTarget = {
  /** 作品总标题那一层。作品编辑页上没有它(那三个字段在上一层写),那时传 null。 */
  work?: WorkIn | null;
  edition: EditionIn;
};

export type PrefillResult = {
  /** 填进去几格。 */
  filled: number;
  /** 本来就有内容、这次没动的有几格。 */
  kept: number;
  /** 标签因为上限没填进去几个。 */
  skippedTags: number;
};

/** 简介优先要中文那一份:两个源都给的时候,中文那份更有用。 */
function preferChinese(values: string[]): string {
  const hasCJK = (text: string) => /[\u4e00-\u9fff]/.test(text);
  return values.find(hasCJK) ?? values[0] ?? "";
}

export function applySuggestions(
  suggestions: SourceSuggestion[],
  target: PrefillTarget,
  options: { overwrite?: boolean } = {},
): PrefillResult {
  const overwrite = options.overwrite ?? false;
  const values = (field: string) =>
    suggestions.filter((item) => item.field === field).map((item) => item.value);

  let filled = 0;
  let kept = 0;

  /** 一格标量字段:空着就填,已经有内容就看是不是要覆盖。 */
  const put = (current: string, next: string, commit: (value: string) => void) => {
    if (!next) return;
    if (current.trim() && !overwrite) {
      kept += 1;
      return;
    }
    if (current === next) return;
    commit(next);
    filled += 1;
  };

  if (target.work) {
    const original = values("original_title")[0] ?? "";
    const title = values("title")[0] || original;
    put(target.work.title, title, (value) => (target.work!.title = value));
    put(target.work.original_title, original, (value) => (target.work!.original_title = value));

    const aliases = [...new Set(values("alias"))].filter(
      (name) => name !== title && name !== original,
    );
    const fresh = aliases.filter((name) => !target.work!.aliases.includes(name));
    if (fresh.length && (!target.work.aliases.length || overwrite)) {
      target.work.aliases = [...new Set([...target.work.aliases, ...fresh])].slice(0, ALIAS_TAKE);
      filled += 1;
    } else if (fresh.length) {
      kept += 1;
    }
  }

  const edition = target.edition;
  put(edition.title, values("edition_title")[0] ?? "", (value) => (edition.title = value));
  put(edition.summary, preferChinese(values("summary")), (value) => (edition.summary = value));
  put(edition.org, values("org")[0] ?? "", (value) => (edition.org = value));
  put(
    edition.published_on,
    values("published_on")[0] ?? "",
    (value) => (edition.published_on = value),
  );
  put(
    edition.release_status,
    values("release_status")[0] ?? "",
    (value) => (edition.release_status = value),
  );

  // 作者与标签是「一条一条」的,不是一格:同名同职位不重复加,各自有上限。
  const seen = new Set(edition.creators.map((link) => `${link.name}|${link.role}`));
  for (const item of suggestions) {
    if (item.field !== "creator") continue;
    const key = `${item.value}|${item.role ?? ""}`;
    if (seen.has(key)) continue;
    if (edition.creators.length >= CREATOR_TAKE) {
      kept += 1;
      continue;
    }
    seen.add(key);
    edition.creators.push({ name: item.value, role: item.role ?? "" });
    filled += 1;
  }

  const tags = [...new Set(values("tag"))].filter((name) => !edition.tags.includes(name));
  const taken = tags.slice(0, Math.max(0, TAG_TAKE - edition.tags.length));
  if (taken.length) {
    edition.tags = [...edition.tags, ...taken];
    filled += taken.length;
  }

  return { filled, kept, skippedTags: tags.length - taken.length };
}

/** 那张外链封面(第一次出现的那一条);没有就是空串。 */
export function coverFrom(suggestions: SourceSuggestion[]): string {
  return suggestions.find((item) => item.field === "cover_url")?.value ?? "";
}

/** 某个字段是哪些源给的 —— 页面上写成「来自 VNDB、Bangumi」。 */
export function sourcesOf(suggestions: SourceSuggestion[], field: string): string[] {
  const names: string[] = [];
  for (const item of suggestions) {
    if (item.field !== field) continue;
    const label = { bangumi: "Bangumi", vndb: "VNDB" }[item.source] ?? item.source;
    if (!names.includes(label)) names.push(label);
  }
  return names;
}
