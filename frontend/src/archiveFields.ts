/** 具体版本的补充档案。不同载体只展示真正适用的格子。 */
export type ArchiveKey =
  | "ended_on" | "subtype" | "region" | "language" | "catalog_code"
  | "homepage" | "engine" | "audience" | "reading_mode" | "content_notice";

export type ArchiveField = { key: ArchiveKey; label: string; placeholder?: string };
const common = (regionLabel: string): ArchiveField[] => [
  { key: "region", label: regionLabel },
  { key: "homepage", label: "官方网站", placeholder: "https://" },
];

export const ARCHIVE_FIELDS: Record<string, ArchiveField[]> = {
  manga: [
    { key: "ended_on", label: "连载结束", placeholder: "未知可留空" },
    { key: "subtype", label: "出版形式" }, ...common("出版地区"),
    { key: "catalog_code", label: "系列 ISBN / 编号" },
    { key: "audience", label: "受众" }, { key: "reading_mode", label: "阅读方向" },
  ],
  light_novel: [
    { key: "ended_on", label: "刊行结束", placeholder: "未知可留空" },
    { key: "subtype", label: "出版形式" }, ...common("出版地区"),
    { key: "language", label: "原始语言" }, { key: "catalog_code", label: "系列 ISBN / 编号" },
  ],
  game: [
    { key: "subtype", label: "游戏形式" }, ...common("开发地区"),
    { key: "language", label: "原始语言" }, { key: "engine", label: "游戏引擎" },
    { key: "content_notice", label: "内容提示" },
  ],
  anime: [
    { key: "ended_on", label: "放送结束", placeholder: "未知可留空" },
    { key: "subtype", label: "动画形式" }, ...common("制作地区"),
    { key: "language", label: "原始语言" }, { key: "content_notice", label: "内容提示" },
  ],
};

export function archiveFieldsOf(mediaType: string): ArchiveField[] {
  return ARCHIVE_FIELDS[mediaType] ?? [];
}

export function hasPlatforms(mediaType: string): boolean {
  return mediaType === "game" || mediaType === "anime";
}
