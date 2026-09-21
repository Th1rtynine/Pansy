"""The JSON side of 作者: the list, one person, and renaming.

作者由作品正文里的名字建出来(`replace_creators`),没有单独的增删接口 —— 作者是全库共用
的词汇。改名到已有的名字或它的别名是合并不是撞名(见 `app/rules.py`),留下的是被改的那一
行,所以改名前能用的 id 改完还能用。
"""

from fastapi import APIRouter, HTTPException

from app.api.schemas import (
    CreatorCreditOut,
    CreatorDetailOut,
    CreatorIn,
    CreatorOut,
    clean_names,
    edition_ref,
)
from app.db import session_scope
from app.fields import parse_aliases
from app.queries import (
    get_creator_or_404,
    load_creator_carriers,
    load_creator_work_counts,
    load_creators_with_usage,
)
from app.rules import rename_creator

router = APIRouter(prefix="/api", tags=["作者"])


@router.get("/creators", response_model=list[CreatorOut])
def list_creators() -> list[CreatorOut]:
    """Every creator, by name, with how many 作品 (`edition_count`) and 作品总标题 (`work_count`)."""
    with session_scope() as session:
        rows = load_creators_with_usage(session)
        counts = load_creator_work_counts(session)
        answer = [
            CreatorOut(
                id=creator.id,
                name=creator.name,
                aliases=parse_aliases(creator.aliases),
                edition_count=edition_count,
                work_count=counts.get(creator.id, 0),
            )
            for creator, edition_count in rows
        ]

    return answer


@router.get("/creators/{creator_id}", response_model=CreatorDetailOut)
def show_creator(creator_id: int) -> CreatorDetailOut:
    """One 作者 and every 作品 they are credited on, each with the role held —— 角色按件记,
    所以一行是一件作品。
    """
    with session_scope() as session:
        creator = get_creator_or_404(session, creator_id)
        rows = load_creator_carriers(session, creator_id)
        counts = load_creator_work_counts(session)

        answer = CreatorDetailOut(
            id=creator.id,
            name=creator.name,
            aliases=parse_aliases(creator.aliases),
            edition_count=len(rows),
            work_count=counts.get(creator.id, 0),
            credits=[
                CreatorCreditOut(edition=edition_ref(edition, work), role=role)
                for work, edition, role in rows
            ],
        )

    return answer


@router.put("/creators/{creator_id}", response_model=CreatorOut)
def update_creator(creator_id: int, body: CreatorIn) -> CreatorOut:
    """Rename one author and rewrite the alias list: 改成已有的名字或它的别名是把两行并起来,留下的是被改的那一行。
    """
    with session_scope() as session:
        creator = get_creator_or_404(session, creator_id)
        refusal = rename_creator(session, creator, body.name, clean_names(body.aliases))
        if refusal:
            raise HTTPException(status_code=400, detail=refusal)

        counts = load_creator_work_counts(session)
        answer = CreatorOut(
            id=creator.id,
            name=creator.name,
            aliases=parse_aliases(creator.aliases),
            edition_count=len(load_creator_carriers(session, creator_id)),
            work_count=counts.get(creator.id, 0),
        )

    return answer
