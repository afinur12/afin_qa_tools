"""Knowledge Management table blocks render from their stored JSON."""

import json

from app.models import KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgePage, KnowledgeSection


def _table_page(db, content):
    section = KnowledgeSection(name="S")
    db.add(section)
    db.flush()
    page = KnowledgePage(section_id=section.id, title="P")
    db.add(page)
    db.flush()
    board = KnowledgeBoard(page_id=page.id)
    db.add(board)
    db.flush()
    db.add(KnowledgeBlock(board_id=board.id, kind=KnowledgeBlockKind.TABLE, content=content))
    db.commit()
    return page


def test_table_renders_header_column_and_clean_cells(client, db_session):
    content = json.dumps({"head_row": False, "head_col": True, "rows": [
        ["Project", "<b>OIDC Authorization Code Flow</b>"],
        ["Branch", "feature-auth-consent<script>bad()</script>"],
    ]})
    html = client.get(f"/knowledge/pages/{_table_page(db_session, content).id}").text
    assert 'class="km-grid has-head-col"' in html
    assert '<td contenteditable="true"><b>OIDC Authorization Code Flow</b></td>' in html
    assert "feature-auth-consent</td>" in html and "bad()" not in html
    assert 'data-km-tbl="head-col" checked' in html
    assert "data-km-table-form" in html


def test_new_tables_have_a_header_row(client, db_session):
    section = KnowledgeSection(name="S")
    db_session.add(section)
    db_session.flush()
    page = KnowledgePage(section_id=section.id, title="P")
    db_session.add(page)
    db_session.flush()
    board = KnowledgeBoard(page_id=page.id)
    db_session.add(board)
    db_session.commit()
    fragment = client.post(f"/knowledge/boards/{board.id}/blocks", data={"kind": "TABLE"}, headers={"X-Requested-With": "fetch"}).text
    assert 'class="km-grid has-head-row"' in fragment
    assert fragment.count("<td") == 9
