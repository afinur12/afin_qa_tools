"""Knowledge Management sections, pages and the page shell."""

from app.models import (
    KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgeLinkTarget, KnowledgePage,
    KnowledgePageLink, KnowledgeSection,
)
from app.routers.knowledge import SECTION_COLORS

FETCH = {"X-Requested-With": "fetch"}


def _section(db, name="Camara icm", position=0):
    section = KnowledgeSection(name=name, position=position)
    db.add(section)
    db.commit()
    db.refresh(section)
    return section


def _page(db, section, title="Consent page", position=0):
    page = KnowledgePage(section_id=section.id, title=title, position=position)
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def test_empty_home_invites_a_first_section_and_marks_the_nav(client):
    html = client.get("/knowledge").text
    assert "Create your first section" in html
    assert 'class="nav-link active" href="/knowledge"' in html


def test_create_sections_take_palette_colours_in_order(client, db_session):
    first = client.post("/knowledge/sections", data={"name": "Camara icm"}, follow_redirects=False)
    second = client.post("/knowledge/sections", data={"name": "TOKEN MANAGER"}, follow_redirects=False)
    assert first.status_code == 303
    sections = db_session.query(KnowledgeSection).order_by(KnowledgeSection.id).all()
    assert [s.color for s in sections] == SECTION_COLORS[:2]
    assert [s.position for s in sections] == [0, 1]
    assert first.headers["location"] == f"/knowledge/sections/{sections[0].id}"


def test_an_empty_section_offers_a_first_page(client, db_session):
    section = _section(db_session)
    html = client.get(f"/knowledge/sections/{section.id}").text
    assert "This section has no pages yet." in html


def test_create_page_opens_it_and_remembers_it(client, db_session):
    section = _section(db_session)
    response = client.post(f"/knowledge/sections/{section.id}/pages", data={"title": "Consent page"}, follow_redirects=False)
    page = db_session.query(KnowledgePage).one()
    assert response.headers["location"] == f"/knowledge/pages/{page.id}"
    view = client.get(f"/knowledge/pages/{page.id}")
    assert 'value="Consent page"' in view.text
    assert view.cookies.get("km_last_page") == str(page.id)


def test_home_reopens_the_last_page_or_falls_back_to_the_first(client, db_session):
    section = _section(db_session)
    first = _page(db_session, section, "First", 0)
    second = _page(db_session, section, "Second", 1)
    client.cookies.set("km_last_page", str(second.id))
    assert client.get("/knowledge", follow_redirects=False).headers["location"] == f"/knowledge/pages/{second.id}"
    client.cookies.set("km_last_page", "999999")
    assert client.get("/knowledge", follow_redirects=False).headers["location"] == f"/knowledge/pages/{first.id}"


def test_edit_section_name_and_only_palette_colours(client, db_session):
    section = _section(db_session)
    client.post(f"/knowledge/sections/{section.id}/edit", data={"name": "Renamed", "color": "#2f9e44"})
    client.post(f"/knowledge/sections/{section.id}/edit", data={"name": "Renamed", "color": "red"})
    db_session.refresh(section)
    assert (section.name, section.color) == ("Renamed", "#2f9e44")


def test_page_title_autosave_returns_json_and_touches_updated_at(client, db_session):
    page = _page(db_session, _section(db_session))
    before = page.updated_at
    response = client.post(f"/knowledge/pages/{page.id}/edit", data={"title": "  New title  "}, headers=FETCH)
    assert response.json() == {"ok": True}
    db_session.refresh(page)
    assert page.title == "New title"
    assert page.updated_at >= before


def test_reorder_sections_and_pages(client, db_session):
    a, b = _section(db_session, "A", 0), _section(db_session, "B", 1)
    client.post("/knowledge/sections/reorder", data={"order": f"{b.id},{a.id}"})
    p1, p2 = _page(db_session, a, "P1", 0), _page(db_session, a, "P2", 1)
    client.post(f"/knowledge/sections/{a.id}/pages/reorder", data={"order": f"{p2.id},{p1.id},999"})
    db_session.expire_all()
    assert (db_session.get(KnowledgeSection, b.id).position, db_session.get(KnowledgeSection, a.id).position) == (0, 1)
    assert [p.title for p in db_session.get(KnowledgeSection, a.id).pages] == ["P2", "P1"]


def test_delete_section_cascades_pages_boards_blocks_and_links(client, db_session):
    section = _section(db_session)
    page = _page(db_session, section)
    board = KnowledgeBoard(page_id=page.id)
    db_session.add(board)
    db_session.flush()
    db_session.add_all([
        KnowledgeBlock(board_id=board.id, kind=KnowledgeBlockKind.TEXT, content="x"),
        KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.STORY, target_id=1),
    ])
    db_session.commit()
    response = client.post(f"/knowledge/sections/{section.id}/delete", follow_redirects=False)
    assert response.status_code == 303
    db_session.expire_all()
    for model in (KnowledgeSection, KnowledgePage, KnowledgeBoard, KnowledgeBlock, KnowledgePageLink):
        assert db_session.query(model).count() == 0


def test_delete_page_returns_to_its_section(client, db_session):
    section = _section(db_session)
    page = _page(db_session, section)
    response = client.post(f"/knowledge/pages/{page.id}/delete", follow_redirects=False)
    assert response.headers["location"] == f"/knowledge/sections/{section.id}"
    assert db_session.query(KnowledgePage).count() == 0


def test_unknown_ids_404(client):
    assert client.get("/knowledge/pages/999").status_code == 404
    assert client.get("/knowledge/sections/999").status_code == 404
    assert client.post("/knowledge/pages/999/edit", data={"title": "x"}).status_code == 404
    assert client.post("/knowledge/sections/999/delete").status_code == 404
