"""Knowledge Management tables: title, column widths / row heights, and
creating a table from pasted content (optionally right after another block)."""

import json

from app.knowledge_sanitize import parse_table
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


def _table(rows, **extra):
    return json.dumps({"head_row": True, "head_col": False, "rows": rows, **extra})


# ── sanitising sizes ─────────────────────────────────────────────────────────

def test_parse_table_keeps_column_widths_and_row_heights_as_clamped_whole_pixels():
    data = parse_table(_table([["a", "b"], ["c", "d"]], col_widths=[150.6, 9000], row_heights=[None, 3]))
    assert data["col_widths"] == [151, 2000]
    assert data["row_heights"] == [None, 20]


def test_parse_table_fits_sizes_to_the_grid():
    # One width too few is filled with the default; extra widths and heights are dropped.
    data = parse_table(_table([["a", "b", "c"]], col_widths=[100, "wide"], row_heights=[40, 50, 60]))
    assert data["col_widths"] == [100, 120, 120]
    assert data["row_heights"] == [40]


def test_parse_table_leaves_sizes_out_when_none_are_set():
    data = parse_table(_table([["a"]], col_widths=[None, "x"], row_heights=[None]))
    assert "col_widths" not in data and "row_heights" not in data
    assert parse_table(_table([["a"]])) == {"head_row": True, "head_col": False, "rows": [["a"]]}


# ── title ────────────────────────────────────────────────────────────────────

def test_table_title_saves_and_renders(client, db_session):
    board = _board(db_session)
    block = _block(db_session, board, KnowledgeBlockKind.TABLE, _table([["MSISDN", "STATUS"]]))
    response = client.post(f"/knowledge/blocks/{block.id}/edit", data={"title": "  Datatest postpaid  "}, headers=FETCH)
    assert response.status_code == 200
    db_session.refresh(block)
    assert block.title == "Datatest postpaid"

    page = client.get(f"/knowledge/pages/{board.page_id}").text
    assert 'value="Datatest postpaid"' in page and "data-km-table-title" in page
    paper = client.get(f"/knowledge/pages/{board.page_id}?paper=1").text
    assert '<div class="km-table-title is-static">Datatest postpaid</div>' in paper


def test_untitled_table_shows_no_title_on_paper(client, db_session):
    board = _board(db_session)
    _block(db_session, board, KnowledgeBlockKind.TABLE, _table([["a"]]))
    assert "km-table-title" not in client.get(f"/knowledge/pages/{board.page_id}?paper=1").text


# ── sizes render ─────────────────────────────────────────────────────────────

def test_column_widths_and_row_heights_render(client, db_session):
    board = _board(db_session)
    _block(db_session, board, KnowledgeBlockKind.TABLE,
           _table([["a", "b"], ["c", "d"]], col_widths=[200, 90], row_heights=[None, 64]))
    html = client.get(f"/knowledge/pages/{board.page_id}").text
    assert 'class="km-grid has-head-row has-col-widths" style="width:290px"' in html
    assert '<colgroup><col style="width:200px"><col style="width:90px"></colgroup>' in html
    assert '<tr><td contenteditable="true">a</td>' in html
    assert '<tr style="height:64px"><td contenteditable="true">c</td>' in html


# ── creating a table from pasted content ─────────────────────────────────────

def test_create_table_with_content(client, db_session):
    board = _board(db_session)
    content = _table([["MSISDN", "STATUS"], ["6281944223954", "ACTIVE<script>x()</script>"]])
    response = client.post(f"/knowledge/boards/{board.id}/blocks", data={"kind": "table", "content": content}, headers=FETCH)
    assert response.status_code == 200
    assert '<td contenteditable="true">MSISDN</td>' in response.text
    db_session.refresh(board)
    assert json.loads(board.blocks[0].content)["rows"] == [["MSISDN", "STATUS"], ["6281944223954", "ACTIVE"]]


def test_create_table_right_after_a_block(client, db_session):
    board = _board(db_session)
    first = _block(db_session, board, KnowledgeBlockKind.TEXT, "one", position=0)
    last = _block(db_session, board, KnowledgeBlockKind.TEXT, "two", position=1)
    client.post(f"/knowledge/boards/{board.id}/blocks",
                data={"kind": "table", "content": _table([["a", "b"], ["c", "d"]]), "after_block_id": str(first.id)}, headers=FETCH)
    db_session.expire_all()
    order = [(b.kind, b.content if b.kind == KnowledgeBlockKind.TEXT else "table") for b in sorted(db_session.get(KnowledgeBoard, board.id).blocks, key=lambda b: b.position)]
    assert order == [(KnowledgeBlockKind.TEXT, "one"), (KnowledgeBlockKind.TABLE, "table"), (KnowledgeBlockKind.TEXT, "two")]
    assert sorted(b.position for b in db_session.get(KnowledgeBoard, board.id).blocks) == [0, 1, 2]
    assert db_session.get(KnowledgeBlock, last.id).position == 2


def test_after_a_block_on_another_board_appends_instead(client, db_session):
    board = _board(db_session)
    other = _board(db_session)
    _block(db_session, board, KnowledgeBlockKind.TEXT, "one", position=0)
    stranger = _block(db_session, other, KnowledgeBlockKind.TEXT, "x", position=0)
    client.post(f"/knowledge/boards/{board.id}/blocks",
                data={"kind": "table", "content": _table([["a"]]), "after_block_id": str(stranger.id)}, headers=FETCH)
    db_session.expire_all()
    blocks = sorted(db_session.get(KnowledgeBoard, board.id).blocks, key=lambda b: b.position)
    assert [b.kind for b in blocks] == [KnowledgeBlockKind.TEXT, KnowledgeBlockKind.TABLE]


def test_content_is_ignored_for_non_table_blocks(client, db_session):
    board = _board(db_session)
    client.post(f"/knowledge/boards/{board.id}/blocks", data={"kind": "text", "content": "<script>x</script>"}, headers=FETCH)
    db_session.refresh(board)
    assert board.blocks[0].content == ""


def test_table_tools_offer_top_or_side_placement(client, db_session):
    board = _board(db_session)
    _block(db_session, board, KnowledgeBlockKind.TABLE, _table([["a"]]))
    html = client.get(f"/knowledge/pages/{board.page_id}").text
    assert 'data-km-tbl="dock"' in html
