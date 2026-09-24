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
  catalog_code: string | null;
  page_count: number | null;
  volume_type: string | null;
  local_path: string | null;
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
  ended_on: string | null;
  cover_url: string | null;
  cover_width: number | null;
  cover_height: number | null;
  summary: string | null;
  org: string | null;
  release_status: string | null;
  volume_count: number | null;
  /** 本机资源入口；当前只保存路径，不由网页直接执行。 */
  local_path: string | null;
  subtype: string | null;
  region: string | null;
  language: string | null;
  catalog_code: string | null;
  homepage: string | null;
  engine: string | null;
  audience: string | null;
  reading_mode: string | null;
  content_notice: string | null;
  platforms: string[];
  organizations: { name: string; role: string }[];
  official_links: { label: string; url: string }[];
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
  ended_on: string;
  summary: string;
  org: string;
  release_status: string;
  volume_count: number | null;
  local_path: string;
  subtype: string;
  region: string;
  language: string;
  catalog_code: string;
  homepage: string;
  engine: string;
  audience: string;
  reading_mode: string;
  content_notice: string;
  platforms: string[];
  organizations: { name: string; role: string }[];
  official_links: { label: string; url: string }[];
  creators: CreatorLinkIn[];
  tags: string[];
};

export type VolumeIn = {
  volume_number: number | null;
  title: string;
  summary: string;
  published_on: string;
  catalog_code?: string;
  page_count?: number | null;
  volume_type?: string;
  local_path?: string;
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
  catalog_code: string | null;
  page_count: number | null;
  volume_type: string | null;
};

// ---- 外部数据源 -----------------------------------------------------------
/**
 * 一个数据源,以及它有没有凭据(`configured` 是 false 也能用,只是少一类内容;Hikarinagi 例外 ——
 * 它没有凭据就完全不能用)。
 */
export type SourceOut = {
  name: string;
  label: string;
  hint: string;
  configured: boolean;
  /** 没有凭据时去哪儿配,一句话(**后端给的**);有凭据、或后端没给时缺省。 */
  configure_hint?: string;
};

// ---- 设置 -----------------------------------------------------------------
/**
 * 一个需要凭据的源现在配成什么样。**`masked` 只是掩码,完整 secret 从不回显。**
 * `fields` 是「还要填哪几格」(键名 → 给人的名字),前端照着画输入框 —— 加一个源不用改前端。
 */
export type CredentialOut = {
  source: string;
  label: string;
  /** 怎么拿到这份凭据,一句话。 */
  hint: string;
  fields: Record<string, string>;
  /** **这个源现在能不能用**,不是「填了几格」—— VNDB 不用凭据也是 true。 */
  configured: boolean;
  /** 没填时那几格是不是必须填。false 且没填 = 不该报警。 */
  optional: boolean;
  /** 存得下但**当前版本不会读它** —— 页面上要如实说。 */
  noop: boolean;
  masked: string;
  /** "settings" = 网页上填的;空串 = 还没填。 */
  from: "" | "settings";
};

/**
 * 某个源上「这个凭据对应谁」。**不带任何令牌**,连掩码都不带 —— 头像与昵称就够认人了。
 *
 * 后端把每个源的原始形状都拉平成了这一套键(Bangumi 的头像在 `images.large`,
 * Hikarinagi 的在 `avatar.src`),所以页面不为每个源各写一遍取值逻辑。
 */
export type AccountOut = {
  /**
   * 这个源的身份**确认过了**(登录成功、或者令牌验证通过)。页面据此收起那一格输入框 ——
   * 验证过了就没有再让人看一遍输入框的道理;凭据一改后端就把资料忘掉,这里又变回 false。
   */
  verified: boolean;
  id: number | null;
  /** 用户名(`name` / Bangumi 的 `username`)。 */
  name: string;
  /** 昵称 —— 显示时优先用它。 */
  nickname: string;
  avatar_url: string;
  bio: string;
  signature: string;
  /** 注册时间。只有 Bangumi 给得出,没有就是空串。 */
  registered_at: string;
};

/**
 * Hikarinagi 那边**登录着谁**(用户级令牌换来的)。比通用形状多三格:
 * `logged_in` 决定页面画「登录」还是「退出登录」,另两格是**该往控制台填什么**(给人照抄用的)。
 */
export type HikarinagiAccountOut = AccountOut & {
  logged_in: boolean;
  /** 本机登录回调地址,要原样填进 Hikarinagi 控制台。 */
  redirect_uri: string;
  /** 这次登录会申请的 scope。控制台里得把对应的格子勾上。 */
  login_scope: string;
  /** 单点登出地址。退出登录之后要把浏览器送过去 —— 只清本地不够。 */
  logout_url: string;
};

/** 要跳去登录的地址。`url` 为空说明现在跳不了,`detail` 里写着为什么。 */
export type HikarinagiLoginOut = {
  url: string;
  detail: string;
};

/**
 * 网页上那些设置现在的样子。**后端永远不回完整令牌**,只回「有没有填」加一个掩码 ——
 * 完整令牌是要拿去授权的东西,回显一次就多一个泄漏面(截图、别人瞟一眼、浏览器缓存)。
 */
export type SettingsOut = {
  bangumi_token_set: boolean;
  /** 形如 `abcd…wxyz`;没填就是空串。拿它认「是不是我填的那个」就够了。 */
  bangumi_token_masked: string;
  /** "settings" = 网页上填的(优先),"config" = `config.toml` 里写的,空串 = 两处都没填。 */
  bangumi_token_from: "" | "settings" | "config";
  /** 有凭据可填的源(眼下是 Hikarinagi 与 VNDB)。 */
  credentials: CredentialOut[];
  /** Hikarinagi 那边登录着谁。没登录时 `logged_in` 为假,其余为空串。 */
  hikarinagi_account: HikarinagiAccountOut;
  /** Bangumi 那个令牌对应谁。**验证过一次之后才有** —— 它不登录,只是拿令牌问了一句「我是谁」。 */
  bangumi_account: AccountOut;
  /** VNDB 那个令牌对应谁。同样验证过一次才有。 */
  vndb_account: AccountOut;
  /** 请求外部源时对外声明的名字。来自 `config.toml`,页面上改不了,只显示。 */
  user_agent: string;
  timeout: number;
  /** 网页设置写到哪去了(相对项目根目录)。 */
  settings_file: string;
  /** 自动预填时从前往后采用；前面的源没有该字段才轮到下一个。 */
  source_priority: string[];
};

/** 拿现在这个令牌问一句 Bangumi 的结果。**不通不是错误,是一个结果。** */
export type TokenCheckOut = { ok: boolean; detail: string };

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
  /** 本次关键词下的相关度；0 表示仅由上游返回、尚未被本地匹配器认出。 */
  match_score: number;
  /** 是否依靠错字容许才命中。 */
  match_approximate: boolean;
};

/** 一个框敲一下之后拿回来的东西。`resolved` 只有敲的是条目 ID 时才有,页面上默认就勾着它;`steps` 是「哪个词搜了哪个源」。 */
export type CollectOut = {
  resolved: SourceCandidate | null;
  steps: { source: string; keyword: string; why: string }[];
  candidates: SourceCandidate[];
  approximate: boolean;
};

/** The source entry chosen to name the shared Work for one selected carrier. */
export type SourceIdentityOut = {
  work: SourceCandidate;
  /** Empty when the carrier names itself; otherwise the relation path followed by the source. */
  relations: string[];
};

export type SourceCounterpartsOut = { items: SourceCandidate[] };

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

export type WorkClaimOut = { work_id: number; work_title: string };

/**
 * 作品家族里的一条:**它是哪一条、凭什么进来的、要不要默认勾上**。
 *
 * `evidence` 是给人看的一句话(「Bangumi 标记为动画改编」)。**不要拿 `confidence` 去算百分比**:
 * 它只有 high / low / unknown 三档,画成数字是在假装精确。
 */
export type FamilyMemberOut = {
  candidate: SourceCandidate;
  /** SAME_WORK / RELATED_WORK / UNKNOWN。 */
  kind: string;
  confidence: string;
  evidence: string;
  /**
   * 要存进作品关系的那一类(related / side_story / adaptation / …)。**直接用它,不要去解析 `evidence`**
   * —— 那句话是给人看的,随时可能改写。
   */
  relation_type: string;
  /**
   * 要存进作品关系的方向:`from_main` = 主作品指向它,`from_related` = 它指向主作品。
   * **后端按关系词定好了**(「动画」与「番外篇」的方向相反),照抄即可,不要自己写死。
   */
  direction: "from_main" | "from_related";
  /** 由哪一条走过来的(种子是空串)。 */
  via: string;
  depth: number;
  selected: boolean;
  /** 这一条本地已经有了 —— 有了就不该再建一件(判重看外部 id,不看标题)。 */
  already_in_library: boolean;
  /** 已经有的话,它现在是哪一件。 */
  claimed_by: ClaimOut | null;
};

/** 要看哪一条的家族。**只读**,不会写任何东西。 */
export type FamilyPreviewIn = {
  source: string;
  external_id: string;
};

/** 一族现在的样子。**一份草稿**:用户确认之前后端一条都不写。 */
export type FamilyPreviewOut = {
  seed: SourceCandidate;
  editions: FamilyMemberOut[];
  related_works: FamilyMemberOut[];
  uncertain: FamilyMemberOut[];
  /** 扫到但**没有**进来当作品的卷:`[属于哪一条, 卷的外部 id]`,要详细内容再按 id 单独问。 */
  volumes: [string, string][];
  /** 少了什么、为什么少。**有它说明结果不完整,但结果仍然可用。** */
  warnings: string[];
  hops: number;
  elapsed: number;
};

/** 加入作品时的**一件**作品:作品自己的字段,加上这一件的外部条目与封面。 */
export type ImportEditionIn = EditionIn & {
  refs: { source: string; external_id: string; title?: string; url?: string }[];
  /** 这一版本所指向的统一作品；保存时用于硬性校验跨作品混选。 */
  identity_ref?: { source: string; external_id: string; title?: string; url?: string } | null;
  /** 采用的那张外链封面;后端会先把它落盘,再写库(写入顺序:先落盘,后写库)。 */
  cover_url?: string;
  /** 这一件底下的卷:页面上读回来、人改过之后的**最终那一份**,保存时随这一件一起提交。 */
  volumes?: VolumeImportIn[];
};

/** 加入作品时的**一卷**:卷自己的字段,加上它的外部条目与封面外链。 */
export type VolumeImportIn = {
  volume_number: number | null;
  title: string;
  summary: string;
  published_on: string;
  catalog_code: string;
  page_count: number | null;
  volume_type: string;
  local_path: string;
  /** 采用的那张外链封面;后端先落盘再写库,取不到就跳过这一卷的图。 */
  cover_url?: string;
  /**
   * 这一卷在来源站上是哪几条(同一卷在两个站上各有一条)。**留着它才能跨来源合并**:下次从另一个
   * 来源导同一卷时,后端靠它认回原来那一行,而不是又建一卷。
   */
  refs?: { source: string; external_id: string; title?: string; url?: string }[];
};

/**
 * 一个关联作品与主作品之间的**有方向**关系。
 *
 * `direction` 说这一条从哪边出发:`from_related` = 「关联作品 → 主作品」(它是主作品的番外篇),
 * `from_main` 反过来。**方向不能省** —— 少了它,「谁是番外篇」就说不清了。
 */
export type WorkImportLinkIn = {
  /** related / prequel / sequel / side_story / spin_off / same_setting / collection / adaptation / unknown。 */
  relation_type: string;
  direction: "from_main" | "from_related";
  source: string;
  /** 来源站的原话,原样留着。 */
  raw_relation?: string | null;
  confidence: string;
};

/** 一个**要真正建出来**的关联作品(例如《安达与岛村99.9》),连同它的件与它和主作品的关系。 */
export type RelatedWorkImportIn = {
  work: WorkIn;
  editions: ImportEditionIn[];
  link: WorkImportLinkIn;
  work_cover_url?: string;
};

/**
 * 加入作品:一次建出「作品总标题 + 它的若干件作品」,每一件各带自己的外部条目。**「只加一件」就是这里只有一项**,不另开一扇门。
 *
 * `related` 是可选的**图**:同一个事务里再建若干部关联作品,并记下它们与主作品的关系。不传就是原来的
 * 行为(一条总标题加它的件)。**扫到但这次不导入的关联作品不要放进来** —— 那会建出一堆空的总标题。
 */
export type ImportIn = {
  work: WorkIn;
  editions: ImportEditionIn[];
  /** 已找到并存在于库里的总作品；有值时本次版本直接归到它下面。 */
  existing_work_id?: number | null;
  work_ref?: { source: string; external_id: string; title?: string; url?: string } | null;
  /** 总标题自己那张封面(原作那一条的图)的外链;留空就不动。 */
  work_cover_url?: string;
  related?: RelatedWorkImportIn[];
};

// ---- 界面上要用的常量 -----------------------------------------------------
/** 排序的两档。取值与后端 `app/listing.py` 的 `WORK_SORTS` 一致(**与后端重复的一处**,改了那边要改这里)。 */
export const WORK_SORTS = [
  { value: "title", label: "按标题" },
  { value: "date", label: "按时间" },
] as const;
