"""Knowledge Management PDF export: the paper view, the section page list and the page hooks."""

from app.models import KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgePage, KnowledgeSection


def _page_with_code(db):
    section = KnowledgeSection(name="Camara icm")
    db.add(section)
    db.flush()
    page = KnowledgePage(section_id=section.id, title="Consent page", position=0)
    db.add(page)
    db.flush()
    board = KnowledgeBoard(page_id=page.id, title="Self test")
    db.add(board)
    db.flush()
    db.add(KnowledgeBlock(board_id=board.id, kind=KnowledgeBlockKind.CODE, content="SELECT 1", language="SQL"))
    db.commit()
    return section, page


def test_paper_view_is_a_standalone_light_page_with_static_code(client, db_session):
    _, page = _page_with_code(db_session)
    html = client.get(f"/knowledge/pages/{page.id}", params={"paper": 1}).text
    assert '<html lang="en" data-theme="light">' in html
    assert 'class="sidebar"' not in html
    assert "data-km-paper-head" in html and "data-km-canvas" in html
    assert '<code class="language-sql" data-km-hljs>SELECT 1</code>' in html
    assert "data-km-code" not in html


def test_section_pages_json_lists_pages_in_order(client, db_session):
    section, page = _page_with_code(db_session)
    second = KnowledgePage(section_id=section.id, title="Test Scenario", position=1)
    db_session.add(second)
    db_session.commit()
    assert client.get(f"/knowledge/sections/{section.id}/pages.json").json() == [
        {"id": page.id, "title": "Consent page"}, {"id": second.id, "title": "Test Scenario"},
    ]
    assert client.get("/knowledge/sections/999/pages.json").status_code == 404


def test_page_has_export_buttons_dialog_and_libraries(client, db_session):
    section, page = _page_with_code(db_session)
    html = client.get(f"/knowledge/pages/{page.id}").text
    assert "data-km-export-page" in html
    assert f'data-km-export-section="{section.id}"' in html
    assert "data-km-export" in html and "km_export_orientation" in html
    assert "html2canvas.min.js" in html and "pdf-lib.min.js" in html and "knowledge_export.js" in html
