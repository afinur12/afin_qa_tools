"""Knowledge Management blocks: create, edit (per kind), reorder, delete."""

import json

from app.models import KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgePage, KnowledgeSection

FETCH = {"X-Requested-With": "fetch"}


def _board(db):
    section = KnowledgeSection(name="S")
    db.add(section)
    db.flush()
    page = KnowledgePage(section_id=section.id, title="P")
    db.add(page)
    db.flush()
    board = KnowledgeBoard(page_id=page.id)
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


def _block(db, board, kind, content="", position=0, **fields):
    block = KnowledgeBlock(board_id=board.id, kind=kind, content=content, position=position, **fields)
    db.add(block)
    db.commit()
    db.refresh(block)
    return block


def test_create_text_code_and_table_blocks_append_in_order(client, db_session):
    board = _board(db_session)
    for kind in ("text", "CODE", "table"):
        assert client.post(f"/knowledge/boards/{board.id}/blocks", data={"kind": kind}, headers=FETCH).status_code == 200
    db_session.refresh(board)
    assert [(b.kind, b.position) for b in board.blocks] == [
        (KnowledgeBlockKind.TEXT, 0), (KnowledgeBlockKind.CODE, 1), (KnowledgeBlockKind.TABLE, 2),
    ]
    assert json.loads(board.blocks[2].content)["head_row"] is True


def test_images_and_files_are_not_created_here(client, db_session):
    board = _board(db_session)
    assert client.post(f"/knowledge/boards/{board.id}/blocks", data={"kind": "IMAGE"}).status_code == 400
    assert client.post(f"/knowledge/boards/{board.id}/blocks", data={"kind": "nonsense"}).status_code == 400


def test_text_edit_is_sanitised_and_can_be_cleared(client, db_session):
    block = _block(db_session, _board(db_session), KnowledgeBlockKind.TEXT, "<p>old</p>")
    client.post(f"/knowledge/blocks/{block.id}/edit", data={"content": '<p onclick="x">hi</p><script>bad()</script>'}, headers=FETCH)
    db_session.refresh(block)
    assert block.content == "<p>hi</p>"
    client.post(f"/knowledge/blocks/{block.id}/edit", data={"content": ""}, headers=FETCH)
    db_session.refresh(block)
    assert block.content == ""


def test_code_edit_keeps_plain_text_title_and_known_language(client, db_session):
    board = _board(db_session)
    block = _block(db_session, board, KnowledgeBlockKind.CODE)
    client.post(f"/knowledge/blocks/{block.id}/edit", data={"content": "<script>x</script>", "title": "decision", "language": "curl"}, headers=FETCH)
    db_session.refresh(block)
    assert (block.content, block.title, block.language) == ("<script>x</script>", "decision", "CURL")
    client.post(f"/knowledge/blocks/{block.id}/edit", data={"language": "cobol"}, headers=FETCH)
    db_session.refresh(block)
    assert block.language == "TEXT"
    html = client.get(f"/knowledge/pages/{board.page_id}").text
    assert "&lt;script&gt;x&lt;/script&gt;" in html


def test_table_edit_is_sanitised(client, db_session):
    block = _block(db_session, _board(db_session), KnowledgeBlockKind.TABLE, '{"rows": [[""]]}')
    raw = json.dumps({"head_row": False, "head_col": True, "rows": [["<b>Project</b>", "<img src=x onerror=y()>"]]})
    client.post(f"/knowledge/blocks/{block.id}/edit", data={"content": raw}, headers=FETCH)
    db_session.refresh(block)
    assert json.loads(block.content) == {"head_row": False, "head_col": True, "rows": [["<b>Project</b>", ""]]}


def test_reorder_blocks(client, db_session):
    board = _board(db_session)
    a = _block(db_session, board, KnowledgeBlockKind.TEXT, "a", 0)
    b = _block(db_session, board, KnowledgeBlockKind.TEXT, "b", 1)
    client.post(f"/knowledge/boards/{board.id}/blocks/reorder", data={"order": f"{b.id},{a.id}"}, headers=FETCH)
    db_session.refresh(board)
    assert [blk.content for blk in board.blocks] == ["b", "a"]


def test_delete_block(client, db_session):
    board = _board(db_session)
    block = _block(db_session, board, KnowledgeBlockKind.TEXT)
    response = client.post(f"/knowledge/blocks/{block.id}/delete", follow_redirects=False)
    assert response.headers["location"] == f"/knowledge/pages/{board.page_id}"
    assert db_session.query(KnowledgeBlock).count() == 0


def test_page_renders_text_code_and_table_markup(client, db_session):
    board = _board(db_session)
    _block(db_session, board, KnowledgeBlockKind.TEXT, "<p>note</p>", 0)
    _block(db_session, board, KnowledgeBlockKind.CODE, "SELECT 1", 1, title="check", language="SQL")
    html = client.get(f"/knowledge/pages/{board.page_id}").text
    assert "data-km-text" in html and "<p>note</p>" in html
    assert "data-km-code" in html and ">SELECT 1</textarea>" in html and 'value="check"' in html
    assert "data-km-add-menu-pop" in html and "data-km-format" in html


def test_block_routes_404(client):
    assert client.post("/knowledge/boards/999/blocks", data={"kind": "TEXT"}).status_code == 404
    assert client.post("/knowledge/blocks/999/edit", data={"content": "x"}).status_code == 404
    assert client.post("/knowledge/boards/999/blocks/reorder", data={"order": ""}).status_code == 404
    assert client.post("/knowledge/blocks/999/delete").status_code == 404
