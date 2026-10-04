"""Knowledge Management image/file uploads, downloads and file cleanup."""

import pytest

import app.routers.knowledge as knowledge_module
import app.routers.screenshots as screenshots_module
from app.models import KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgePage, KnowledgeSection

FETCH = {"X-Requested-With": "fetch"}
PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture(autouse=True)
def uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(screenshots_module, "UPLOADS_DIR", tmp_path)
    compressed = []
    monkeypatch.setattr(knowledge_module, "compress_in_background", compressed.append)
    return {"root": tmp_path, "compressed": compressed}


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


def test_png_upload_becomes_an_image_block_and_is_compressed(client, db_session, uploads):
    board = _board(db_session)
    response = client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("shot.png", PNG, "image/png")}, headers=FETCH)
    block = db_session.query(KnowledgeBlock).one()
    assert block.kind == KnowledgeBlockKind.IMAGE
    assert block.file_path.startswith(f"knowledge/{board.page_id}/") and block.file_path.endswith(".png")
    assert (block.file_name, block.file_size, block.content_type) == ("shot.png", len(PNG), "image/png")
    assert (uploads["root"] / block.file_path).read_bytes() == PNG
    assert len(uploads["compressed"]) == 1
    assert f'src="/uploads/{block.file_path}"' in response.text


def test_other_files_become_file_blocks_and_download_with_their_name(client, db_session):
    board = _board(db_session)
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("API Specs.pdf", b"%PDF-1.7 data", "application/pdf")}, headers=FETCH)
    block = db_session.query(KnowledgeBlock).one()
    assert block.kind == KnowledgeBlockKind.FILE
    download = client.get(f"/knowledge/blocks/{block.id}/download")
    assert download.content == b"%PDF-1.7 data"
    assert 'filename="API Specs.pdf"' in download.headers["content-disposition"]
    page = client.get(f"/knowledge/pages/{board.page_id}").text
    assert "API Specs.pdf" in page and f"/knowledge/blocks/{block.id}/download" in page and "13 B" in page


def test_upload_over_the_limit_is_refused(client, db_session, monkeypatch):
    monkeypatch.setattr(knowledge_module, "MAX_UPLOAD_BYTES", 10)
    board = _board(db_session)
    response = client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("big.bin", b"x" * 11, "application/octet-stream")})
    assert response.status_code == 413
    assert db_session.query(KnowledgeBlock).count() == 0


def test_deleting_blocks_and_pages_removes_their_files(client, db_session, uploads):
    board = _board(db_session)
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("a.png", PNG, "image/png")}, headers=FETCH)
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("b.txt", b"hello", "text/plain")}, headers=FETCH)
    first, second = db_session.query(KnowledgeBlock).order_by(KnowledgeBlock.id).all()
    assert (uploads["root"] / first.file_path).exists() and (uploads["root"] / second.file_path).exists()
    client.post(f"/knowledge/blocks/{first.id}/delete")
    assert not (uploads["root"] / first.file_path).exists()
    client.post(f"/knowledge/pages/{board.page_id}/delete")
    assert not (uploads["root"] / second.file_path).exists()


def test_caption_saves_on_image_blocks(client, db_session):
    board = _board(db_session)
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("a.png", PNG, "image/png")}, headers=FETCH)
    block = db_session.query(KnowledgeBlock).one()
    client.post(f"/knowledge/blocks/{block.id}/edit", data={"content": " Response of /decision "}, headers=FETCH)
    db_session.refresh(block)
    assert block.content == "Response of /decision"


def test_upload_and_download_404(client, db_session):
    assert client.post("/knowledge/boards/999/upload", files={"file": ("a.png", PNG, "image/png")}).status_code == 404
    assert client.get("/knowledge/blocks/999/download").status_code == 404


def test_svg_is_stored_as_a_file_not_an_image(client, db_session):
    board = _board(db_session)
    svg = b"<svg xmlns='http://www.w3.org/2000/svg'/>"
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("logo.svg", svg, "image/svg+xml")}, headers=FETCH)
    assert db_session.query(KnowledgeBlock).one().kind == KnowledgeBlockKind.FILE


def test_stored_extension_keeps_only_letters_and_digits(client, db_session):
    board = _board(db_session)
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("x.txt:stream", b"data", "text/plain")}, headers=FETCH)
    client.post(f"/knowledge/boards/{board.id}/upload", files={"file": ("y.a<b", b"data", "application/octet-stream")}, headers=FETCH)
    paths = [b.file_path for b in db_session.query(KnowledgeBlock).order_by(KnowledgeBlock.id)]
    assert paths[0].endswith(".txtstream") and paths[1].endswith(".ab")


def test_download_header_survives_quotes_and_accents(client, db_session, uploads):
    board = _board(db_session)
    (uploads["root"] / "knowledge").mkdir()
    (uploads["root"] / "knowledge" / "f.pdf").write_bytes(b"%PDF")
    block = KnowledgeBlock(
        board_id=board.id, position=0, kind=KnowledgeBlockKind.FILE, file_path="knowledge/f.pdf",
        file_name='Résumé "x".pdf', content_type="application/pdf",
    )
    db_session.add(block)
    db_session.commit()
    disposition = client.get(f"/knowledge/blocks/{block.id}/download").headers["content-disposition"]
    assert disposition == "attachment; filename=\"R_sum_ _x_.pdf\"; filename*=utf-8''R%C3%A9sum%C3%A9%20%22x%22.pdf"
