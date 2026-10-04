"""Knowledge Management tables round-trip through SQLite."""

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import (
    KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgeLinkTarget, KnowledgePage,
    KnowledgePageLink, KnowledgeSection,
)


def test_knowledge_tree_round_trips(db_session):
    section = KnowledgeSection(name="Camara icm")
    db_session.add(section)
    db_session.flush()
    page = KnowledgePage(section_id=section.id, title="Consent page")
    db_session.add(page)
    db_session.flush()
    board = KnowledgeBoard(page_id=page.id, z=1)
    db_session.add(board)
    db_session.flush()
    db_session.add_all([
        KnowledgeBlock(board_id=board.id, position=1, kind=KnowledgeBlockKind.CODE, content="curl x", language="CURL"),
        KnowledgeBlock(board_id=board.id, position=0, kind=KnowledgeBlockKind.TEXT, content="<p>hi</p>"),
        KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.STORY, target_id=7),
    ])
    db_session.commit()
    db_session.expire_all()

    loaded = db_session.get(KnowledgeSection, section.id)
    assert loaded.color == "#9b9aa4"
    assert [p.title for p in loaded.pages] == ["Consent page"]
    loaded_board = loaded.pages[0].boards[0]
    assert (loaded_board.x, loaded_board.y, loaded_board.width, loaded_board.height) == (20, 20, 380, None)
    assert [b.kind for b in loaded_board.blocks] == [KnowledgeBlockKind.TEXT, KnowledgeBlockKind.CODE]
    assert loaded.pages[0].links[0].target_type == KnowledgeLinkTarget.STORY


def test_a_page_links_to_the_same_target_only_once(db_session):
    section = KnowledgeSection(name="S")
    db_session.add(section)
    db_session.flush()
    page = KnowledgePage(section_id=section.id)
    db_session.add(page)
    db_session.flush()
    db_session.add(KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.SUBTASK, target_id=3))
    db_session.commit()
    db_session.add(KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.SUBTASK, target_id=3))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
