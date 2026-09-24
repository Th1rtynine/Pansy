"""把搜索框里的词对到一行的各个可搜字段上;纯字符串函数,不碰 session / 请求 / 模板。

近失误六种:大小写、标点与全角、空格、拼音、一两个错字、拼音本身的错字。前四种是子串判断,
不会凭空造出结果;后两种在标题的**任意一段**上比编辑距离,只在前面一无所获时才跑。词整体折成
一段、不按空格拆 —— 程序分不出 "zhou shu" 与 "shu zhou",拆了就是在替输入断言词序。容差见
typo_tolerance。
"""

import unicodedata
from dataclasses import dataclass

from pypinyin import lazy_pinyin


def normalize(text: str) -> str:
    """折成可以比较的样子:小写、半角、只留字母与数字。
    "Fate/stay night" 与 "fate stay" 都是 fatestaynight。丢掉非字母数字而不是列出标点,顺带
    盖住中日文的标点(isalnum() 也不认它们)。
    """
    folded = unicodedata.normalize("NFKC", text)
    return "".join(character for character in folded.lower() if character.isalnum())


def pinyin_of(text: str) -> str:
    """Latin spelling of the Chinese characters; everything else passes through."""
    return "".join(lazy_pinyin(text))


def keyword_text(raw: str) -> str:
    """The whole keyword as one comparable run; an empty keyword gives ""."""
    return normalize(raw)


def retry_keywords(raw: str, maximum: int = 8) -> list[str]:
    """给外部数据源的保守重试词。

    外部站点若拿错字搜回空表,本地相关度就没有候选可排。这里不猜一个所谓“正确标题”,只生成
    能跨过一次多字、漏字或错字的短查询:先去掉首尾一字,再取稳定的前后半段,最后尝试去掉中间
    一字。返回顺序就是尝试顺序;调用方一旦找回与原词近似的候选便停止。

    两个汉字已经足以向中文源取候选;纯拉丁文字至少留三个字符,免得把整个站都捞回来。
    """
    text = (raw or "").strip()
    positions = [index for index, character in enumerate(text) if character.isalnum()]
    if len(positions) < 3 or maximum <= 0:
        return []

    minimum = 2 if any("\u3400" <= character <= "\u9fff" for character in text) else 3
    found: list[str] = []

    def add(value: str) -> None:
        candidate = value.strip()
        if (
            candidate
            and candidate != text
            and len(normalize(candidate)) >= minimum
            and candidate not in found
        ):
            found.append(candidate)

    # 三个汉字没有可再切开的两段,逐个删一字。虚词优先,「无的限」会先试「无限」;
    # 其次是末尾与开头,「无限的」第一次便试「无限」。
    if len(positions) < minimum * 2:
        particles = "的地得了着过啊呀呢吗吧是"
        ordered = [index for index in positions if text[index] in particles]
        ordered += [positions[-1], positions[0], *positions[1:-1]]
        for index in dict.fromkeys(ordered):
            add(text[:index] + text[index + 1 :])
        return found[:maximum]

    # 更长的词只问互不重叠的前后两段。一处多字、漏字或错字至多污染一段,另一段仍能把候选
    # 带回来;同时把一次搜索的额外外部请求严格限制为两轮。
    if len(positions) >= minimum * 2:
        span = max(minimum, len(positions) // 2)
        add(text[: positions[span - 1] + 1])
        add(text[positions[-span] :])

    return found[:maximum]


@dataclass(frozen=True)
class SearchEntry:
    """库里的一行,缩成搜索框要比的那些值。
    row_id 由调用方定。库在两个层级上用同一份代码搜:作品 id 一次,载体 id 一次。
    每个值带着字段名,命中了才说得出命中哪个字段;逐个比而不连成一串,也是为这个。
    """

    row_id: int
    # (字段名, 折好的值),一个值一对。
    fields: tuple[tuple[str, str], ...]
    # 同样的值再存一份拉丁拼写,给拼音关键词用;两者容差不同,见 typo_kinds。
    spellings: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class SearchHit:
    """一行为什么命中、排在什么位置。

    分数只在**同一次搜索**里比较,不是要存进数据库的绝对值。`approximate` 为真说明这一轮
    依靠的是错字容许;页面可以据此明确告诉人「这不是完全匹配」。
    """

    row_id: int
    kinds: tuple[str, ...]
    score: int
    approximate: bool = False


def build_entry(row_id: int, values: list[tuple[str, str]]) -> SearchEntry:
    """Reduce the (field name, raw text) pairs of one row to a SearchEntry."""
    fields = tuple(
        (kind, folded) for kind, value in values if (folded := normalize(value))
    )
    spellings = tuple(
        (kind, folded) for kind, value in values if (folded := normalize(pinyin_of(value)))
    )
    return SearchEntry(row_id=row_id, fields=fields, spellings=spellings)


def distance(left: str, right: str) -> int:
    """Levenshtein distance: how many single-character edits turn one into the other."""
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)

    previous = list(range(len(right) + 1))
    for row, left_character in enumerate(left, start=1):
        current = [row]
        for column, right_character in enumerate(right, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (left_character != right_character),
                )
            )
        previous = current
    return previous[-1]


def approx_contains(text: str, pattern: str, limit: int) -> bool:
    """pattern 是否与 text 的某一段相差不超过 limit 个编辑?
    还是那张编辑距离表,两处不同:第一行全零(匹配可以从 text 任意处开始),答案是最后一行
    里最小的值(可以到任意处结束)。代价与比整串相同,所以兜底能对每一行的每个值都跑。
    """
    if not pattern or not text:
        return False
    # pattern 的每个字符对上一个空位也要花这么多。
    if len(text) < len(pattern) - limit:
        return False

    previous = [0] * (len(text) + 1)
    for row, pattern_character in enumerate(pattern, start=1):
        current = [row]
        for column, text_character in enumerate(text, start=1):
            current.append(
                min(
                    previous[column] + 1,
                    current[column - 1] + 1,
                    previous[column - 1] + (pattern_character != text_character),
                )
            )
        # 匹配更长的 pattern 前缀不会更便宜,所以整行都超限之后,后面的行只会更差。
        if min(current) > limit:
            return False
        previous = current

    return min(previous) <= limit


def typo_tolerance(text: str) -> int:
    """允许错几个字符。短关键词一个都不许。

    两个字母的关键词与太多东西只差一个编辑,所以兜底直接关掉,不让它猜。
    """
    if len(text) <= 2:
        return 0
    if len(text) <= 4:
        return 1
    return 2


# 拼写按子串比而不是整串:拼音关键词通常只是罗马化的一段。所以容差更小 ——
# 六个字母的关键词与长罗马化里许多无关片段都只差两个编辑:zoushu 与知识 (zhishu)、
# 周刊少年 (zhouka)、轻小说 (qingxiaoshuo) 都只差两个。
SPELLING_TOLERANCE = 1

# 字段负责消歧:同样是完全命中,正式标题应排在原名、别名与作者/标签之前。没有列在这里的
# 字段仍然可搜,只是同分时不抢过标题。
_FIELD_BONUS = {
    "作品总标题": 80,
    "作品标题": 80,
    "标题": 80,
    "原名": 60,
    "别名": 40,
}


def _field_bonus(kind: str) -> int:
    return _FIELD_BONUS.get(kind, 0)


def _substring_score(value: str, text: str, kind: str, *, spelling: bool) -> int:
    """一个值的相关度。层与层之间留足间隔,长度与位置只能在同一层里打破平手。"""
    if text not in value:
        return 0

    bonus = _field_bonus(kind)
    length_penalty = min(60, max(0, len(value) - len(text)))
    if spelling:
        if value == text:
            base = 620
        elif value.startswith(text):
            base = 560
        else:
            base = 500 - min(60, value.index(text))
    else:
        if value == text:
            base = 1000
        elif value.startswith(text):
            base = 850
        else:
            base = 700 - min(80, value.index(text))
    return max(1, base + bonus - length_penalty)


def _near_score(value: str, text: str, kind: str, *, spelling: bool, limit: int) -> int:
    """错字兜底的分数。它永远低于任何子串/拼音命中。"""
    bonus = _field_bonus(kind)
    if spelling:
        if not approx_contains(value, text, SPELLING_TOLERANCE):
            return 0
        return 300 + bonus - min(60, max(0, len(value) - len(text)))

    edits = distance(value, text)
    if edits <= limit:
        return 420 + bonus - edits * 45 - min(40, abs(len(value) - len(text)))

    # 查询可以只是长标题的一部分。过去这里只拿整条标题比,「无限的」对「无限斯特拉斯」会被
    # 后面尚未输入的四个字拖成不匹配;现在只要求标题中有一段与查询相差不超过容差。
    if not approx_contains(value, text, limit):
        return 0
    return 360 + bonus - min(60, max(0, len(value) - len(text)))


def _rank(entries: list[SearchEntry], keyword: str, *, approximate: bool) -> list[SearchHit]:
    text = keyword_text(keyword)
    limit = typo_tolerance(text)
    if not text or (approximate and not limit):
        return []

    hits: list[SearchHit] = []
    for entry in entries:
        scores: list[tuple[str, int]] = []
        for kind, value in entry.fields:
            score = (
                _near_score(value, text, kind, spelling=False, limit=limit)
                if approximate
                else _substring_score(value, text, kind, spelling=False)
            )
            if score:
                scores.append((kind, score))
        for kind, value in entry.spellings:
            score = (
                _near_score(value, text, kind, spelling=True, limit=limit)
                if approximate
                else _substring_score(value, text, kind, spelling=True)
            )
            if score:
                scores.append((kind, score))
        if not scores:
            continue
        hits.append(
            SearchHit(
                row_id=entry.row_id,
                kinds=tuple(dict.fromkeys(kind for kind, _score in scores)),
                score=max(score for _kind, score in scores),
                approximate=approximate,
            )
        )

    # row_id 是稳定的最后一道消歧;调用方仍可在同分时追加标题或时间。
    return sorted(hits, key=lambda hit: (-hit.score, hit.row_id))


def rank_match(entries: list[SearchEntry], keyword: str) -> list[SearchHit]:
    """标准化文本、子串与拼音的相关度排序。"""
    return _rank(entries, keyword, approximate=False)


def rank_near_match(entries: list[SearchEntry], keyword: str) -> list[SearchHit]:
    """只有标准匹配全空时才使用的错字排序。"""
    return _rank(entries, keyword, approximate=True)


def substring_kinds(entry: SearchEntry, text: str) -> list[str]:
    """这一行里值或拼写含关键词的那些字段。
    一条可能答出好几个:关键词可以同时落在标签和某卷的名字里。
    """
    kinds = [kind for kind, value in entry.fields if text in value]
    kinds += [kind for kind, value in entry.spellings if text in value]
    return list(dict.fromkeys(kinds))


def typo_kinds(entry: SearchEntry, text: str, limit: int) -> list[str]:
    """关键词几乎等于的那些字段(按给定容差)。原值整串比,可以用满容差:两个字母换位 —— "Fate/Zreo"
    打给 Fate/Zero —— 就已经算两个编辑;拼写走更小的子串容差。
    """
    kinds = [
        kind
        for kind, value in entry.fields
        if distance(value, text) <= limit or approx_contains(value, text, limit)
    ]
    kinds += [
        kind
        for kind, value in entry.spellings
        if approx_contains(value, text, SPELLING_TOLERANCE)
    ]
    return list(dict.fromkeys(kinds))


def match(entries: list[SearchEntry], keyword: str) -> dict[int, list[str]]:
    """{行 id: 值或拼写含关键词的字段} —— 第 1 到 4 步,不会凭空造出结果。
    空答案就是答案:库里没有你打的东西。
    """
    return {hit.row_id: list(hit.kinds) for hit in rank_match(entries, keyword)}


def near_match(entries: list[SearchEntry], keyword: str) -> dict[int, list[str]]:
    """{行 id: 关键词几乎等于的那些字段} —— 第 5 和第 6 步。只在 `match` 一无所获时才值得问。
    它比编辑距离、能凭空造出结果,所以调用方要知道是它:页面写「未找到完全匹配的结果」时,得确保确实
    没有精确命中。
    """
    return {hit.row_id: list(hit.kinds) for hit in rank_near_match(entries, keyword)}
