"""Knowledge Management boards: create, geometry, batch positions, title, delete."""

from app.models import KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgePage, KnowledgeSection

FETCH = {"X-Requested-With": "fetch"}


def _page(db):
    section = KnowledgeSection(name="Camara icm")
    db.add(section)
    db.flush()
    page = KnowledgePage(section_id=section.id, title="Consent page")
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def _board(db, page, **fields):
    board = KnowledgeBoard(page_id=page.id, **fields)
    db.add(board)
    db.commit()
    db.refresh(board)
    return board


def test_create_board_returns_its_fragment_with_one_empty_text_block(client, db_session):
    page = _page(db_session)
    _board(db_session, page, z=4)
    response = client.post(f"/knowledge/pages/{page.id}/boards", data={"x": "-30", "y": "524"}, headers=FETCH)
    board = db_session.query(KnowledgeBoard).order_by(KnowledgeBoard.id.desc()).first()
    assert (board.x, board.y, board.width, board.height, board.z) == (0, 524, 380, None, 5)
    assert [b.kind for b in board.blocks] == [KnowledgeBlockKind.TEXT]
    assert f'data-board-id="{board.id}"' in response.text
    assert "data-km-text" in response.text


def test_geometry_saves_and_clamps(client, db_session):
    board = _board(db_session, _page(db_session))
    client.post(f"/knowledge/boards/{board.id}/geometry", data={"x": "40", "y": "60", "width": "100", "height": "50", "z": "3"}, headers=FETCH)
    db_session.refresh(board)
    assert (board.x, board.y, board.width, board.height, board.z) == (40, 60, 220, 80, 3)
    client.post(f"/knowledge/boards/{board.id}/geometry", data={"x": "40", "y": "60", "width": "500", "height": "", "z": "3"}, headers=FETCH)
    db_session.refresh(board)
    assert (board.width, board.height) == (500, None)


def test_batch_positions_only_touch_this_pages_boards(client, db_session):
    page = _page(db_session)
    mine = _board(db_session, page, y=20)
    other = _board(db_session, _page(db_session), y=20)
    response = client.post(
        f"/knowledge/pages/{page.id}/boards/positions",
        json=[{"id": mine.id, "y": 640}, {"id": other.id, "y": 999}, {"id": mine.id, "y": "bad"}, "junk"],
    )
    assert response.json() == {"updated": 1}
    db_session.expire_all()
    assert (db_session.get(KnowledgeBoard, mine.id).y, db_session.get(KnowledgeBoard, other.id).y) == (640, 20)
    assert client.post(f"/knowledge/pages/{page.id}/boards/positions", content="nope").status_code == 400


def test_batch_positions_ignore_anything_that_is_not_a_real_int_id(client, db_session):
    page = _page(db_session)
    mine = _board(db_session, page, id=1, y=20)  # id 1 so that `True` would match it
    other = _board(db_session, _page(db_session), y=20)
    response = client.post(
        f"/knowledge/pages/{page.id}/boards/positions",
        json=[
            {"id": mine.id, "y": 640},
            {"id": [1], "y": 1},
            {"id": {"x": 1}, "y": 1},
            {"id": True, "y": 1},
            {"id": mine.id, "y": 700},
            {"id": other.id, "y": 999},
        ],
    )
    assert response.status_code == 200
    assert response.json() == {"updated": 1}
    db_session.expire_all()
    assert (db_session.get(KnowledgeBoard, mine.id).y, db_session.get(KnowledgeBoard, other.id).y) == (640, 20)


def test_board_title_is_trimmed(client, db_session):
    board = _board(db_session, _page(db_session))
    assert client.post(f"/knowledge/boards/{board.id}/edit", data={"title": "  Project  "}, headers=FETCH).json() == {"ok": True}
    db_session.refresh(board)
    assert board.title == "Project"


def test_delete_board_removes_its_blocks_and_returns_to_the_page(client, db_session):
    page = _page(db_session)
    board = _board(db_session, page)
    db_session.add(KnowledgeBlock(board_id=board.id, kind=KnowledgeBlockKind.TEXT, content="x"))
    db_session.commit()
    response = client.post(f"/knowledge/boards/{board.id}/delete", follow_redirects=False)
    assert response.headers["location"] == f"/knowledge/pages/{page.id}"
    assert db_session.query(KnowledgeBoard).count() == 0
    assert db_session.query(KnowledgeBlock).count() == 0


def test_page_renders_boards_where_they_were_left(client, db_session):
    page = _page(db_session)
    board = _board(db_session, page, x=560, y=40, width=320, height=300, z=2, title="Note")
    db_session.add(KnowledgeBlock(board_id=board.id, kind=KnowledgeBlockKind.TEXT, content="<p>Auto <b>HE</b></p><script>x()</script>"))
    db_session.commit()
    html = client.get(f"/knowledge/pages/{page.id}").text
    assert "left:560px; top:40px; width:320px; height:300px; z-index:2;" in html
    assert 'value="Note"' in html
    assert "<p>Auto <b>HE</b></p>" in html
    assert "x()" not in html


def test_board_routes_404_for_unknown_ids(client):
    assert client.post("/knowledge/pages/999/boards", data={"x": "0", "y": "0"}).status_code == 404
    assert client.post("/knowledge/boards/999/geometry", data={"x": "0", "y": "0", "width": "300", "z": "0"}).status_code == 404
    assert client.post("/knowledge/boards/999/edit", data={"title": "x"}).status_code == 404
    assert client.post("/knowledge/boards/999/delete").status_code == 404
    assert client.post("/knowledge/pages/999/boards/positions", json=[]).status_code == 404
