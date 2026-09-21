"""把搜索框里的词对到一行的各个可搜字段上;纯字符串函数,不碰 session / 请求 / 模板。

近失误六种:大小写、标点与全角、空格、拼音、一两个错字、拼音本身的错字。前四种是子串判断,
不会凭空造出结果;后两种比编辑距离,只在前面一无所获时才跑。词整体折成一段、不按空格拆 ——
程序分不出 "zhou shu" 与 "shu zhou",拆了就是在替输入断言词序。容差见 typo_tolerance。
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
    kinds = [kind for kind, value in entry.fields if distance(value, text) <= limit]
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
    text = keyword_text(keyword)
    if not text:
        return {}
    return {
        entry.row_id: kinds for entry in entries if (kinds := substring_kinds(entry, text))
    }


def near_match(entries: list[SearchEntry], keyword: str) -> dict[int, list[str]]:
    """{行 id: 关键词几乎等于的那些字段} —— 第 5 和第 6 步。只在 `match` 一无所获时才值得问。
    它比编辑距离、能凭空造出结果,所以调用方要知道是它:页面写「未找到完全匹配的结果」时,得确保确实
    没有精确命中。
    """
    text = keyword_text(keyword)
    limit = typo_tolerance(text)
    if not text or not limit:
        return {}
    return {
        entry.row_id: kinds for entry in entries if (kinds := typo_kinds(entry, text, limit))
    }
