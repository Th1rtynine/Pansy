/** 接口回来的、以及要送上去的东西的形状。与后端 `app/api/schemas.py` 一个对一个:那边改了字段名这里要跟着改,改了这里不会有任何东西报错。 */

// ---- 回来的 ---------------------------------------------------------------
/** 一份作品的摘要。列表、关联、作者页与标签页的一行都用它。 */
export type EditionRef = {
  id: number;
  work_id: number;
  work_title: string;
  media_type: string;
  /** 「漫画」「动画」这类给人看的名字,后端给,前端不自己抄一份。 */
  media_label: string;
  title: string | null;
  published_on: string | null;
  /** 封面地址(`/covers/...`);没有封面时是 null,由 Cover.vue 画占位。 */
  cover_url: string | null;
  /** 原图像素尺寸:图还没到时按真实比例占位,版式不会跳一下;读不出尺寸时是 null,退回 3:4。 */
  cover_width: number | null;
  cover_height: number | null;
};

/** 作品列表里的一行:摘要再加上这次搜索命中在哪一项。 */
export type EditionRowOut = EditionRef & { matched_by: string[] };

export type VolumeOut = {
  id: number;
  edition_id: number;
  volume_number: number | null;
  title: string | null;
  summary: string | null;
  /** 发售日;写多少算多少(「2006」「2006-05」「2006-05-24」),没写就是 null。 */
  published_on: string | null;
  /** 这一卷自己的封面;没有时是 null,由 Cover.vue 画占位。 */
  cover_url: string | null;
  cover_width: number | null;
  cover_height: number | null;
};

export type CreatorLinkOut = { id: number; name: string; role: string };

export type TagRef = { id: number; name: string; media_type: string; media_label: string };

export type EditionOut = {
  id: number;
  work_id: number;
  work_title: string;
  media_type: string;
  media_label: string;
  /** 这个类型记哪几项、每项叫什么 —— 后端的 MEDIA_TYPE_FIELDS 那一行。 */
  fields: Record<string, string>;
  title: string | null;
  published_on: string | null;
  cover_url: string | null;
  cover_width: number | null;
  cover_height: number | null;
  summary: string | null;
  org: string | null;
  release_status: string | null;
  volume_count: number | null;
  creators: CreatorLinkOut[];
  tags: TagRef[];
  volumes: VolumeOut[];
  relations: EditionRef[];
};

/** 一件作品总标题,连同它的作品。 */
export type WorkOut = {
  id: number;
  title: string;
  original_title: string | null;
  aliases: string[];
  /** 原作时间:它下面最早的那份作品的时间。它自己不存这一列。 */
  published_on: string | null;
  /** **这一部想用的那张图**:总标题自己传过就用它,没传过沿用第一件的封面;两个都空时是 null。 */
  cover_url: string | null;
  cover_width: number | null;
  cover_height: number | null;
  editions: EditionRef[];
  /** 这次搜索是命中在哪一项上的(「标签」「作者」…);没有搜索时是空的。 */
  matched_by: string[];
};

export type LinkedWorkOut = {
  id: number;
  title: string;
  published_on: string | null;
  edition_count: number;
};

export type WorkDetailOut = WorkOut & {
  editions: EditionOut[];
  linked_works: LinkedWorkOut[];
};

export type WorkListOut = {
  total: number;
  page: number;
  pages: number;
  page_size: number;
  sort: string;
  keyword: string;
  approximate: boolean;
  items: WorkOut[];
};

export type EditionListOut = {
  total: number;
  page: number;
  pages: number;
  page_size: number;
  sort: string;
  keyword: string;
  media_type: string;
  approximate: boolean;
  items: EditionRowOut[];
};

export type CreatorOut = {
  id: number;
  name: string;
  aliases: string[];
  edition_count: number;
  work_count: number;
};

export type CreatorCreditOut = { edition: EditionRef; role: string };

export type CreatorDetailOut = CreatorOut & { credits: CreatorCreditOut[] };

export type TagOut = TagRef & { edition_count: number };

export type TagDetailOut = TagOut & { editions: EditionRef[] };

/** 一个媒体类型:取值、名字、它记哪几项。 */
export type MediaTypeOut = {
  value: string;
  label: string;
  fields: Record<string, string>;
};

// ---- 送上去的 -------------------------------------------------------------
export type WorkIn = {
  title: string;
  original_title: string;
  aliases: string[];
};

export type CreatorLinkIn = { name: string; role: string };

export type EditionIn = {
  media_type: string;
  title: string;
  published_on: string;
  summary: string;
  org: string;
  release_status: string;
  volume_count: number | null;
  creators: CreatorLinkIn[];
  tags: string[];
};

export type VolumeIn = {
  volume_number: number | null;
  title: string;
  summary: string;
  published_on: string;
};

/** 从源里读回来的一卷草稿(选中一条系列条目之后问来的)。它**不是候选**:卷由我们自己的卷表记;`cover_url` 是外链,保存时由后端取回来落盘。 */
export type SourceVolume = {
  source: string;
  external_id: string;
  number: number | null;
  title: string | null;
  published_on: string | null;
  summary: string | null;
  cover_url: string | null;
};

// ---- 外部数据源 -----------------------------------------------------------
/** 一个数据源,以及它有没有凭据(`configured` 是 false 也能用,只是少一类内容)。 */
export type SourceOut = { name: string; label: string; hint: string; configured: boolean };

/** 搜索结果里的一条。**够认出「是不是它」就行** —— 详情等选中了再取。 */
export type SourceCandidate = {
  source: string;
  external_id: string;
  /** 这一条在源上是不是「系列」(一部作品的上一层,卷挂在它底下),页面靠它决定要不要去问卷;分不出这一层的源一律 false。 */
  series: boolean;
  title: string;
  original_title: string | null;
  year: string | null;
  kind: string | null;
  cover_url: string | null;
  /** 后端**猜**的类型(manga / light_novel / game / anime),猜不出来是 null;只用来分组与给表单初值,建的时候类型还是要人点一次。 */
  media: string | null;
  /** 归一化后的名字(后端算的),两个源上的同一条作品靠它归到一组:`CLANNAD` 与 `CLANNAD -クラナド-` 一组,`〜AFTER STORY〜` 另算一组。 */
  group: string;
  /** 别名。只有「按 id 取回一条」时才有。 */
  aliases: string[];
};

/** 一个框敲一下之后拿回来的东西。`resolved` 只有敲的是条目 ID 时才有,页面上默认就勾着它;`steps` 是「哪个词搜了哪个源」。 */
export type CollectOut = {
  resolved: SourceCandidate | null;
  steps: { source: string; keyword: string; why: string }[];
  candidates: SourceCandidate[];
};

/** The source entry chosen to name the shared Work for one selected carrier. */
export type SourceIdentityOut = {
  work: SourceCandidate;
  /** Empty when the carrier names itself; otherwise the relation path followed by the source. */
  relations: string[];
};

/** 挑中的一件作品:同一个名字下的若干条候选说的是同一条记录。**一个源在一件作品上最多一条**,所以按源分;`key` 是那一组在页面上的名字,靠它保住往同一组里再勾一个源时已填好的格子。 */
export type PickedCarrier = {
  key: string;
  media: string;
  name: string;
  items: SourceCandidate[];
};

/**
 * 一条逐字段的建议。**字段名是我们自己的词汇**,后端已把两家的字段翻译成这一套:
 * title / original_title / alias / edition_title / summary / org / published_on / release_status / creator / tag / cover_url
 */
export type SourceSuggestion = {
  field: string;
  value: string;
  source: string;
  external_id: string;
  url: string;
  role: string | null;
  excerpt: string | null;
};

/** 「这条作品在那个站上是哪一条」。 */
export type SourceRefOut = {
  source: string;
  external_id: string;
  title: string | null;
  url: string | null;
  fetched_at: string | null;
};

/** 某个外部条目已经被库里的哪一条认领了(没人认领时接口回 null)。 */
export type ClaimOut = {
  edition_id: number;
  work_id: number;
  work_title: string;
  edition_title: string | null;
};

/** 加入作品时的**一件**作品:作品自己的字段,加上这一件的外部条目与封面。 */
export type ImportEditionIn = EditionIn & {
  refs: { source: string; external_id: string; title?: string; url?: string }[];
  /** 采用的那张外链封面;后端会先把它落盘,再写库(写入顺序:先落盘,后写库)。 */
  cover_url?: string;
};

/** 加入作品:一次建出「作品总标题 + 它的若干件作品」,每一件各带自己的外部条目。**「只加一件」就是这里只有一项**,不另开一扇门。 */
export type ImportIn = {
  work: WorkIn;
  editions: ImportEditionIn[];
};

// ---- 界面上要用的常量 -----------------------------------------------------
/** 排序的两档。取值与后端 `app/listing.py` 的 `WORK_SORTS` 一致(**与后端重复的一处**,改了那边要改这里)。 */
export const WORK_SORTS = [
  { value: "title", label: "按标题" },
  { value: "date", label: "按时间" },
] as const;
