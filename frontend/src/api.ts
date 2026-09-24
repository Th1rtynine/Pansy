/**
 * 与后端说话的唯一出口。后端在 `/api` 下,出错一律回 `{"detail": "…"}`,那句话就是页面上显示
 * 的中文,所以这里把非 2xx 变成 `ApiError`,消息直接取它,页面不自己编。地址只写在这里一处。
 * 下面是按实体分好的小对象;开发时 `/api` 由 Vite 转给后端(见 vite.config.ts),写相对地址即可。
 */

import type {
  ClaimOut,
  CollectOut,
  CreatorDetailOut,
  CreatorOut,
  EditionIn,
  EditionListOut,
  EditionOut,
  EditionRef,
  FamilyPreviewIn,
  FamilyPreviewOut,
  ImportIn,
  MediaTypeOut,
  HikarinagiAccountOut,
  HikarinagiLoginOut,
  SourceCandidate,
  SourceCounterpartsOut,
  SourceVolume,
  SourceIdentityOut,
  SourceOut,
  SourceRefOut,
  SourceSuggestion,
  SettingsOut,
  TagDetailOut,
  TagOut,
  TokenCheckOut,
  VolumeIn,
  VolumeOut,
  VolumesAddedOut,
  WorkDetailOut,
  WorkClaimOut,
  WorkIn,
  WorkListOut,
  WorkOut,
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * 传一个文件(**multipart**)。身体是 `FormData`,**不能自己挂 `Content-Type`** ——
 * boundary 得由浏览器写。出错那一套与 `request()` 一样。
 */
async function upload<T>(path: string, file: File): Promise<T> {
  const body = new FormData();
  body.append("file", file);
  const answer = await fetch(`/api${path}`, { method: "POST", body });

  if (!answer.ok) {
    let detail = `请求失败(${answer.status})`;
    try {
      const parsed = (await answer.json()) as { detail?: unknown };
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
      else if (parsed && parsed.detail) detail = JSON.stringify(parsed.detail);
    } catch {
      // 回的不是 JSON,就留下上面那句兜底的话。
    }
    throw new ApiError(detail, answer.status);
  }

  return (await answer.json()) as T;
}

async function request<T>(method: string, path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const answer = await fetch(`/api${path}`, {
    method,
    headers: body === undefined ? undefined : { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });

  if (!answer.ok) {
    let detail = `请求失败(${answer.status})`;
    try {
      const parsed = (await answer.json()) as { detail?: unknown };
      if (parsed && typeof parsed.detail === "string") detail = parsed.detail;
      else if (parsed && parsed.detail) detail = JSON.stringify(parsed.detail);
    } catch {
      // 回的不是 JSON,就留下上面那句兜底的话。
    }
    throw new ApiError(detail, answer.status);
  }

  if (answer.status === 204) return undefined as T;
  return (await answer.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, signal?: AbortSignal) => request<T>("POST", path, body, signal),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  remove: (path: string) => request<void>("DELETE", path),
};

/**
 * 把查询参数拼成 `?a=1&b=2`;空字符串与 undefined 丢掉 —— 后端那边「没传」与「传了空」
 * 是同一件事(例如 `media_type=` 就是全部四类)。
 */
export function query(params: Record<string, string | number | undefined>): string {
  const pairs = Object.entries(params)
    .filter(([, value]) => value !== undefined && value !== "")
    .map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(String(value))}`);
  return pairs.length ? `?${pairs.join("&")}` : "";
}

export const meta = {
  mediaTypes: () => api.get<{ items: MediaTypeOut[] }>("/media-types"),
};

export const works = {
  list: (params: { q?: string; sort?: string; page?: number } = {}) =>
    api.get<WorkListOut>(`/works${query(params)}`),
  get: (id: number) => api.get<WorkDetailOut>(`/works/${id}`),
  create: (body: WorkIn) => api.post<WorkOut>("/works", body),
  /** 一个事务里建出作品总标题与它的若干件作品;回的是这一部作品的详情。 */
  createWithEditions: (body: ImportIn) => api.post<WorkDetailOut>("/works/with-editions", body),
  update: (id: number, body: WorkIn) => api.put<WorkOut>(`/works/${id}`, body),
  remove: (id: number) => api.remove(`/works/${id}`),
  /** 传总标题自己的封面,走 multipart;没传过时读取那一侧沿用第一件的封面。 */
  uploadCover: (id: number, file: File) => upload<WorkOut>(`/works/${id}/cover`, file),
  /** 摘掉总标题自己的封面。**硬盘上那个文件留着**;页面上回到第一件那张。 */
  clearCover: (id: number) => request<WorkOut>("DELETE", `/works/${id}/cover`),
};

/** 外部数据源。页面只认这一组名字;要搜哪几个源是调用时传的。 */
export const sources = {
  list: () => api.get<SourceOut[]>("/sources"),
  search: (keyword: string, names: string[] = []) =>
    api.post<SourceCandidate[]>("/sources/search", { keyword, sources: names }),
  /** **那一个框**:名字或条目 ID 都收。后端先补全(id → 名字与别名),再拿补全后的名字搜每个源。 */
  collect: (query: string, signal?: AbortSignal) =>
    api.post<CollectOut>("/sources/collect", { query }, signal),
  /** 补全的第一步单独用:按 id 取回这一条(取不到是 404)。 */
  resolve: (source: string, externalId: string) =>
    api.post<SourceCandidate>("/sources/resolve", { source, external_id: externalId }),
  /** Find which source entry should supply the shared Work title for this carrier. */
  identity: (source: string, externalId: string) =>
    api.post<SourceIdentityOut>("/sources/identity", { source, external_id: externalId }),
  /** 只按来源条目自带的跨站编号补齐同一具体版本；不靠标题猜。 */
  counterparts: (source: string, externalId: string) =>
    api.post<SourceCounterpartsOut>("/sources/counterparts", { source, external_id: externalId }),
  workClaim: (source: string, externalId: string) =>
    api.get<WorkClaimOut | null>(`/sources/work-claims${query({ source, external_id: externalId })}`),
  suggest: (picks: { source: string; external_id: string }[]) =>
    api.post<SourceSuggestion[]>("/sources/suggest", { picks }),
  /** 这个外部条目已经被库里哪一条认领了;没人认领回 null。 */
  claims: (source: string, externalId: string) =>
    api.get<ClaimOut | null>(`/sources/claims${query({ source, external_id: externalId })}`),
  /** 一条系列条目**底下**的卷(只读):选中「这一部」之后再单独问它,保存时随作品一起提交。 */
  volumes: (source: string, externalId: string) =>
    api.get<SourceVolume[]>(`/sources/volumes${query({ source, external_id: externalId })}`),
  /**
   * 这一条所在的「一族」:同一作品的其他版本、关联作品、以及判不下来的那些。**只读,不写库。**
   *
   * 单独一趟而不是塞进 `collect`:它要顺着关系图走几步,慢得多。分开之后慢的这一段不影响搜索手感,
   * 而且它拿不到一部分时会**带着一部分回来**(`warnings` 里说明),不会把整趟拖垮。
   */
  familyPreview: (source: string, externalId: string) =>
    api.post<FamilyPreviewOut>("/sources/family-preview", {
      source,
      external_id: externalId,
    } satisfies FamilyPreviewIn),
  /** 让后端按页面当前所在的 origin 生成登录地址;开发版与构建版不必共用一个写死端口。 */
  hikarinagiLogin: (redirectUri: string, chooseAccount = false) =>
    api.get<HikarinagiLoginOut>(
      `/sources/hikarinagi/login${query({ redirect_uri: redirectUri, choose_account: chooseAccount })}`,
    ),
  /** 退出登录:后端先让服务端把那枚长期凭证作废,再清掉本地那一份。 */
  hikarinagiLogout: () => api.remove<HikarinagiAccountOut>("/sources/hikarinagi/login"),
  refs: (editionId: number) => api.get<SourceRefOut[]>(`/editions/${editionId}/source-refs`),
  remember: (
    editionId: number,
    body: { source: string; external_id: string; title?: string; url?: string },
  ) => api.put<SourceRefOut>(`/editions/${editionId}/source-refs`, body),
  forget: (editionId: number, source: string) =>
    api.remove(`/editions/${editionId}/source-refs/${source}`),
};

export const editions = {
  list: (params: { q?: string; media_type?: string; sort?: string; page?: number } = {}) =>
    api.get<EditionListOut>(`/editions${query(params)}`),
  get: (id: number) => api.get<EditionOut>(`/editions/${id}`),
  create: (workId: number, body: EditionIn) =>
    api.post<EditionOut>(`/works/${workId}/editions`, body),
  update: (id: number, body: EditionIn) => api.put<EditionOut>(`/editions/${id}`, body),
  remove: (id: number) => api.remove(`/editions/${id}`),
  openLocal: (id: number) => api.post<{ ok: boolean; detail: string }>(`/editions/${id}/open-local`, {}),

  /** 还能关联的作品。哪几个不算候选由后端定。 */
  candidates: (id: number) => api.get<EditionRef[]>(`/editions/${id}/relation-candidates`),
  link: (id: number, otherId: number) =>
    api.post<{ edition_a_id: number; edition_b_id: number }>(`/editions/${id}/relations`, {
      other_id: otherId,
    }),
  unlink: (id: number, otherId: number) => api.remove(`/editions/${id}/relations/${otherId}`),
};

export const volumes = {
  list: (editionId: number) => api.get<VolumeOut[]>(`/editions/${editionId}/volumes`),
  add: (editionId: number, items: VolumeIn[]) =>
    api.post<VolumesAddedOut>(`/editions/${editionId}/volumes`, items),
  get: (id: number) => api.get<VolumeOut>(`/volumes/${id}`),
  update: (id: number, body: VolumeIn) => api.put<VolumeOut>(`/volumes/${id}`, body),
  remove: (id: number) => api.remove(`/volumes/${id}`),
  /** 传这一卷的封面(自己扫的那张图),走 multipart;后端认得四种格式、8MB 上限。 */
  uploadCover: (id: number, file: File) => upload<VolumeOut>(`/volumes/${id}/cover`, file),
  /** 摘掉这一卷的封面;硬盘上那个文件留着,换错了一张还能指回去。 */
  clearCover: (id: number) => request<VolumeOut>("DELETE", `/volumes/${id}/cover`),
};

export const creators = {
  list: () => api.get<CreatorOut[]>("/creators"),
  get: (id: number) => api.get<CreatorDetailOut>(`/creators/${id}`),
  rename: (id: number, body: { name: string; aliases: string[] }) =>
    api.put<CreatorOut>(`/creators/${id}`, body),
};

export const tags = {
  list: (mediaType = "") => api.get<TagOut[]>(`/tags${query({ media_type: mediaType })}`),
  get: (id: number) => api.get<TagDetailOut>(`/tags/${id}`),
  rename: (id: number, name: string) => api.put<TagOut>(`/tags/${id}`, { name }),
};

/**
 * 网页上改得动的那几项设置。**回话里没有完整令牌** —— 后端只给「有没有填」和掩码,
 * 所以这一页永远拿不回自己填过的那串字符,这是有意的(见后端 `app/api/settings.py`)。
 */
export const settings = {
  get: () => api.get<SettingsOut>("/settings"),
  /** 传空串就是清掉;写了一串就先存下来,对不对由 `checkToken` 单独问。 */
  saveToken: (bangumiToken: string) =>
    api.put<SettingsOut>("/settings", { bangumi_token: bangumiToken }),
  /** 写某一个源的成对凭据(眼下只有 Hikarinagi)。两格要一起给。 */
  saveCredentials: (source: string, fields: Record<string, string>) =>
    api.put<SettingsOut>("/settings", { source, fields }),
  saveSourcePriority: (sourcePriority: string[]) =>
    api.put<SettingsOut>("/settings", { source_priority: sourcePriority }),
  /** 把网页上那一份整个抹掉,回到只认 `config.toml` 的状态。 */
  clear: () => api.remove("/settings"),
  /** 拿现在这个令牌去问一句 Bangumi。**不通也回 200**,`ok` 才是结论。 */
  checkToken: () => api.post<TokenCheckOut>("/settings/bangumi-token/check"),
  /** 拿 VNDB 那枚令牌去问一句「这是谁」。同样不通也回 200。这一格是可选的。 */
  checkVndbToken: () => api.post<TokenCheckOut>("/settings/vndb-token/check"),
};
