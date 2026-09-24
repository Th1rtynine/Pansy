"""把夹具当成一个假 Bangumi 用:两个测试文件共用这一段。

**为什么不各写一份**:`test-family.py` 考分类、`test-family-traversal.py` 考遍历,而两者都要
「拿夹具回答关系与条目」。各写一份就会漂开 —— 一边改了取值方式,另一边还在按老形状读,于是同一个
夹具在两个测试里给出不同结论。

**它只读夹具,不连网**:条目从 `entries[<id>].entry` 取,关系从 `entries[<id>].relations` 取,
「原作」那几个目标从 `origin_titles` 取。文件名叫 `family_fixture`(下划线)而不是 `test_*`,
免得被测试收集器当成一个没有断言的测试文件。
"""

from __future__ import annotations

import json
import pathlib

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURE = PROJECT_ROOT / "tests" / "fixtures" / "bangumi-family.json"

DEFAULT_SOURCE = "bangumi"


def load_sample() -> dict:
    """整份夹具。读不出来就是空的那一份(与库里其它读 JSON 的地方同一个规矩)。"""
    try:
        parsed = json.loads(FIXTURE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def seed_of(sample: dict, external_id: str) -> dict:
    return ((sample.get("entries") or {}).get(str(external_id)) or {}).get("entry") or {}


class FakeBangumi:
    """按夹具回答的一个假源。接口与 `app.sources.bangumi.Bangumi` 那三个方法一致。"""

    name = "bangumi"
    label = "Bangumi"

    def __init__(self, sample: dict) -> None:
        self.sample = sample
        self.asked_relations: list[str] = []
        self.asked_fetch: list[str] = []

    def _entries(self) -> dict:
        return self.sample.get("entries") or {}

    def _relations(self, external_id: str) -> list[dict]:
        found = (self._entries().get(str(external_id)) or {}).get("relations") or []
        return [item for item in found if isinstance(item, dict)]

    def _origin(self, external_id: str) -> dict[str, dict]:
        """这一条的「原作」目标各自补到的条目(夹具里单独抓过一份,因为关系表没有 `platform`)。"""
        found = (self.sample.get("origin_titles") or {}).get(str(external_id)) or []
        return {str(item.get("id")): item for item in found if isinstance(item, dict)}

    def fetch(self, external_id: str):
        from app.sources.bangumi import guess_media
        from app.sources.base import Candidate

        self.asked_fetch.append(str(external_id))
        entry = seed_of(self.sample, external_id)
        if not entry:
            # 关系表里出现、但没单独抓过详情的那几条(例如各卷):只回名字与类型。
            for item in self._all_relation_items():
                if str(item.get("id")) == str(external_id):
                    return Candidate(
                        source=self.name,
                        external_id=str(external_id),
                        title=str(item.get("name_cn") or item.get("name") or ""),
                        original_title=item.get("name") or None,
                        cover_url=((item.get("images") or {}).get("large") or None),
                        media=guess_media(item.get("type"), item.get("platform")),
                    )
            return None
        from app.sources.base import Candidate

        return Candidate(
            source=self.name,
            external_id=str(entry.get("id") or external_id),
            title=str(entry.get("name_cn") or entry.get("name") or ""),
            original_title=entry.get("name") or None,
            year=str(entry.get("date") or "")[:4] or None,
            kind=entry.get("platform") or None,
            cover_url=((entry.get("images") or {}).get("large") or None),
            media=guess_media(entry.get("type"), entry.get("platform")),
        )

    def _all_relation_items(self) -> list[dict]:
        return [item for iid in self._entries() for item in self._relations(iid)]

    def relations_of(self, external_id: str):
        from app.sources.bangumi import guess_media
        from app.sources import family
        from app.sources.base import Candidate, SourceRelation

        self.asked_relations.append(str(external_id))
        seed = self.fetch(external_id)
        origins = self._origin(external_id)
        found = []
        for item in self._relations(external_id):
            if item.get("id") is None:
                continue
            target_id = str(item["id"])
            # 「原作」的目标单独抓过详情:合并进来,`platform` 就有值了。
            detail = origins.get(target_id) or {}
            title = str(detail.get("name_cn") or item.get("name_cn") or item.get("name") or "")
            platform = detail.get("platform") or item.get("platform")
            media = guess_media(detail.get("type", item.get("type")), platform)
            candidate = Candidate(
                source=self.name,
                external_id=target_id,
                title=title,
                original_title=item.get("name") or None,
                kind=str(platform or "") or None,
                cover_url=((item.get("images") or {}).get("large") or None),
                media=media,
            )
            raw = str(item.get("relation") or "")
            canonical, confidence, evidence = family.classify(
                relation=raw,
                seed_media=seed.media if seed else None,
                seed_title=(seed.title or seed.original_title) if seed else None,
                target_media=media,
                target_kind=candidate.kind,
                target_platform=str(platform or "") or None,
                target_title=title,
            )
            found.append(
                SourceRelation(
                    source=self.name,
                    from_external_id=str(external_id),
                    to_external_id=target_id,
                    candidate=candidate,
                    raw_relation=raw,
                    canonical=canonical,
                    direction="out",
                    confidence=confidence,
                    evidence=evidence,
                )
            )
        return found
