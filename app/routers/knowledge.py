"""Knowledge Management: OneNote-style sections -> pages -> canvas boards ->
blocks (text, code, image, file, table), linked to stories and subtasks and
exportable to PDF.

Design: docs/superpowers/specs/2026-10-04-knowledge-management-design.md
"""

import mimetypes
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from markupsafe import Markup
from sqlalchemy.orm import Session

import app.routers.screenshots as screenshots_module
from app import deletion
from app.database import get_db
from app.flash import redirect_with_flash
from app.image_compress import compress_in_background
from app.knowledge_sanitize import (
    EMPTY_TABLE_JSON, parse_table, sanitize_cell_html, sanitize_table_json, sanitize_text_html,
)
from app.models import KnowledgeBlock, KnowledgeBlockKind, KnowledgeBoard, KnowledgePage, KnowledgeSection
from app.templating import templates

router = APIRouter()

SECTION_COLORS = ["#9b9aa4", "#d6336c", "#2f9e44", "#1c7ed6", "#e8590c", "#7048e8", "#0c8599", "#f08c00"]
LAST_PAGE_COOKIE = "km_last_page"
DEFAULT_BOARD_WIDTH = 380
MIN_BOARD_WIDTH = 220
MIN_BOARD_HEIGHT = 80
CREATABLE_KINDS = {KnowledgeBlockKind.TEXT, KnowledgeBlockKind.CODE, KnowledgeBlockKind.TABLE}
# Same language codes as app.js's detectSnippetLanguage / HLJS_LANGUAGE_MAP.
KM_HLJS = {
    "CURL": "bash", "JSON": "json", "SQL": "sql", "TEXT": "plaintext", "YAML": "yaml",
    "XML": "xml", "BASH": "bash", "PYTHON": "python", "JAVASCRIPT": "javascript",
}
CODE_LANGUAGES = set(KM_HLJS)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
templates.env.globals["km_hljs"] = KM_HLJS


def _human_size(size: int | None) -> str:
    if not size:
        return "0 B"
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.0f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


# Stored HTML is sanitised on save; rendering through the same allowlist again
# means a row changed outside the app still can't inject markup.
templates.env.filters["km_text"] = lambda html: Markup(sanitize_text_html(html))
templates.env.filters["km_cell"] = lambda html: Markup(sanitize_cell_html(html))
templates.env.filters["km_table"] = parse_table
templates.env.filters["km_size"] = _human_size
# Plain-string twins (autoescaped) for attribute values, e.g. hidden inputs.
templates.env.filters["km_clean"] = sanitize_text_html
templates.env.filters["km_table_json"] = sanitize_table_json


def _is_fetch(request: Request) -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def _not_found(request: Request):
    return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)


def _touch(page: KnowledgePage) -> None:
    # UTC, naive — the same clock as created_at's SQLite CURRENT_TIMESTAMP.
    page.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)


def _sections(db: Session) -> list[KnowledgeSection]:
    return db.query(KnowledgeSection).order_by(KnowledgeSection.position, KnowledgeSection.id).all()


def _parse_order(order: str) -> list[int]:
    return [int(part) for part in order.split(",") if part.strip().isdigit()]


def _link_views(db: Session, page: KnowledgePage) -> list[dict]:
    return []


def _render(request: Request, db: Session, section: KnowledgeSection | None = None, page: KnowledgePage | None = None):
    if section is None and page is not None:
        section = page.section
    response = templates.TemplateResponse(
        request,
        "knowledge/index.html",
        {
            "sections": _sections(db),
            "active_section": section,
            "page": page,
            "section_colors": SECTION_COLORS,
            "link_views": _link_views(db, page) if page is not None else [],
        },
    )
    if page is not None:
        response.set_cookie(LAST_PAGE_COOKIE, str(page.id), max_age=60 * 60 * 24 * 365, path="/")
    return response


# ── Sections and pages ──────────────────────────────────────────────────

@router.get("/knowledge")
def knowledge_home(request: Request, db: Session = Depends(get_db)):
    last = request.cookies.get(LAST_PAGE_COOKIE, "")
    page = db.get(KnowledgePage, int(last)) if last.isdigit() else None
    if page is None:
        first_section = next(iter(_sections(db)), None)
        if first_section is None or not first_section.pages:
            return _render(request, db, section=first_section)
        page = first_section.pages[0]
    return RedirectResponse(f"/knowledge/pages/{page.id}", status_code=303)


@router.get("/knowledge/sections/{section_id}")
def open_section(request: Request, section_id: int, db: Session = Depends(get_db)):
    section = db.get(KnowledgeSection, section_id)
    if section is None:
        return _not_found(request)
    if section.pages:
        return RedirectResponse(f"/knowledge/pages/{section.pages[0].id}", status_code=303)
    return _render(request, db, section=section)


@router.get("/knowledge/pages/{page_id}")
def open_page(request: Request, page_id: int, db: Session = Depends(get_db)):
    page = db.get(KnowledgePage, page_id)
    if page is None:
        return _not_found(request)
    return _render(request, db, page=page)


@router.post("/knowledge/sections")
def create_section(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    sections = _sections(db)
    section = KnowledgeSection(
        name=name.strip()[:200] or "Untitled section",
        color=SECTION_COLORS[len(sections) % len(SECTION_COLORS)],
        position=max((s.position for s in sections), default=-1) + 1,
    )
    db.add(section)
    db.commit()
    return redirect_with_flash(f"/knowledge/sections/{section.id}", f'Section "{section.name}" created.')


@router.post("/knowledge/sections/reorder")
def reorder_sections(order: str = Form(""), db: Session = Depends(get_db)):
    by_id = {s.id: s for s in _sections(db)}
    for position, section_id in enumerate(i for i in _parse_order(order) if i in by_id):
        by_id[section_id].position = position
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/knowledge/sections/{section_id}/edit")
def edit_section(
    request: Request, section_id: int, name: str = Form(...), color: str = Form(""), db: Session = Depends(get_db)
):
    section = db.get(KnowledgeSection, section_id)
    if section is None:
        return _not_found(request)
    section.name = name.strip()[:200] or section.name
    if color in SECTION_COLORS:
        section.color = color
    db.commit()
    return redirect_with_flash(f"/knowledge/sections/{section.id}", "Section saved.")


@router.post("/knowledge/sections/{section_id}/delete")
def delete_section(request: Request, section_id: int, db: Session = Depends(get_db)):
    section = db.get(KnowledgeSection, section_id)
    if section is None:
        return _not_found(request)
    name = section.name
    deletion.delete_knowledge_section(db, section)
    db.commit()
    return redirect_with_flash("/knowledge", f'Section "{name}" deleted.', category="danger")


@router.post("/knowledge/sections/{section_id}/pages")
def create_page(request: Request, section_id: int, title: str = Form("Untitled page"), db: Session = Depends(get_db)):
    section = db.get(KnowledgeSection, section_id)
    if section is None:
        return _not_found(request)
    page = KnowledgePage(
        section_id=section.id,
        title=title.strip()[:300] or "Untitled page",
        position=max((p.position for p in section.pages), default=-1) + 1,
    )
    db.add(page)
    db.commit()
    return RedirectResponse(f"/knowledge/pages/{page.id}", status_code=303)


@router.post("/knowledge/sections/{section_id}/pages/reorder")
def reorder_pages(request: Request, section_id: int, order: str = Form(""), db: Session = Depends(get_db)):
    section = db.get(KnowledgeSection, section_id)
    if section is None:
        return _not_found(request)
    by_id = {p.id: p for p in section.pages}
    for position, page_id in enumerate(i for i in _parse_order(order) if i in by_id):
        by_id[page_id].position = position
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/knowledge/pages/{page_id}/edit")
def edit_page(request: Request, page_id: int, title: str = Form(...), db: Session = Depends(get_db)):
    page = db.get(KnowledgePage, page_id)
    if page is None:
        return _not_found(request)
    page.title = title.strip()[:300] or "Untitled page"
    _touch(page)
    db.commit()
    if _is_fetch(request):
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/knowledge/pages/{page.id}", status_code=303)


@router.post("/knowledge/pages/{page_id}/delete")
def delete_page(request: Request, page_id: int, db: Session = Depends(get_db)):
    page = db.get(KnowledgePage, page_id)
    if page is None:
        return _not_found(request)
    section_id, title = page.section_id, page.title
    deletion.delete_knowledge_page(db, page)
    db.commit()
    return redirect_with_flash(f"/knowledge/sections/{section_id}", f'Page "{title}" deleted.', category="danger")


# ── Boards ──────────────────────────────────────────────────────────────

@router.post("/knowledge/pages/{page_id}/boards")
def create_board(request: Request, page_id: int, x: int = Form(20), y: int = Form(20), db: Session = Depends(get_db)):
    page = db.get(KnowledgePage, page_id)
    if page is None:
        return _not_found(request)
    board = KnowledgeBoard(
        page_id=page.id, x=max(0, x), y=max(0, y), width=DEFAULT_BOARD_WIDTH,
        z=max((b.z for b in page.boards), default=0) + 1,
    )
    db.add(board)
    db.flush()
    db.add(KnowledgeBlock(board_id=board.id, position=0, kind=KnowledgeBlockKind.TEXT, content=""))
    _touch(page)
    db.commit()
    db.refresh(board)
    return templates.TemplateResponse(request, "knowledge/_board_fragment.html", {"item": board})


@router.post("/knowledge/boards/{board_id}/edit")
def edit_board(request: Request, board_id: int, title: str = Form(""), db: Session = Depends(get_db)):
    board = db.get(KnowledgeBoard, board_id)
    if board is None:
        return _not_found(request)
    board.title = title.strip()[:200]
    _touch(board.page)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/knowledge/boards/{board_id}/geometry")
def board_geometry(
    request: Request, board_id: int, x: int = Form(...), y: int = Form(...), width: int = Form(...),
    height: str = Form(""), z: int = Form(0), db: Session = Depends(get_db),
):
    board = db.get(KnowledgeBoard, board_id)
    if board is None:
        return _not_found(request)
    board.x, board.y = max(0, x), max(0, y)
    board.width = max(MIN_BOARD_WIDTH, width)
    board.height = max(MIN_BOARD_HEIGHT, int(height)) if height.strip().isdigit() else None
    board.z = max(0, z)
    _touch(board.page)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/knowledge/pages/{page_id}/boards/positions")
async def board_positions(request: Request, page_id: int, db: Session = Depends(get_db)):
    page = db.get(KnowledgePage, page_id)
    if page is None:
        return _not_found(request)
    try:
        moves = await request.json()
    except ValueError:
        return JSONResponse({"error": "Expected a JSON list of {id, y}."}, status_code=400)
    if not isinstance(moves, list):
        return JSONResponse({"error": "Expected a JSON list of {id, y}."}, status_code=400)
    boards = {b.id: b for b in page.boards}
    seen: set[int] = set()
    updated = 0
    for move in moves:
        if not isinstance(move, dict):
            continue
        board_id, y = move.get("id"), move.get("y")
        # Real ints only: bool is an int subclass (True == 1) and a list/dict id is unhashable.
        if type(board_id) is not int or type(y) is not int or board_id in seen:
            continue
        board = boards.get(board_id)
        if board is None:
            continue
        seen.add(board_id)
        board.y = max(0, y)
        updated += 1
    if updated:
        _touch(page)
    db.commit()
    return JSONResponse({"updated": updated})


@router.post("/knowledge/boards/{board_id}/delete")
def delete_board(request: Request, board_id: int, db: Session = Depends(get_db)):
    board = db.get(KnowledgeBoard, board_id)
    if board is None:
        return _not_found(request)
    page = board.page
    deletion.delete_knowledge_board(db, board)
    _touch(page)
    db.commit()
    if _is_fetch(request):
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/knowledge/pages/{page.id}", status_code=303)


# ── Blocks ──────────────────────────────────────────────────────────────

def _next_block_position(board: KnowledgeBoard) -> int:
    return max((b.position for b in board.blocks), default=-1) + 1


@router.post("/knowledge/boards/{board_id}/blocks")
def create_block(request: Request, board_id: int, kind: str = Form(...), db: Session = Depends(get_db)):
    board = db.get(KnowledgeBoard, board_id)
    if board is None:
        return _not_found(request)
    try:
        block_kind = KnowledgeBlockKind(kind.strip().upper())
    except ValueError:
        return JSONResponse({"error": f"Unknown block kind {kind!r}."}, status_code=400)
    if block_kind not in CREATABLE_KINDS:
        return JSONResponse({"error": "Images and files are added by uploading."}, status_code=400)
    block = KnowledgeBlock(
        board_id=board.id, position=_next_block_position(board), kind=block_kind,
        content=EMPTY_TABLE_JSON if block_kind == KnowledgeBlockKind.TABLE else "",
    )
    db.add(block)
    _touch(board.page)
    db.commit()
    db.refresh(block)
    return templates.TemplateResponse(request, "knowledge/_block_fragment.html", {"item": block})


@router.post("/knowledge/blocks/{block_id}/edit")
async def edit_block(request: Request, block_id: int, db: Session = Depends(get_db)):
    """Reads the raw form on purpose: FastAPI turns an empty Form() field into
    its default, which would make clearing a block impossible."""
    block = db.get(KnowledgeBlock, block_id)
    if block is None:
        return _not_found(request)
    data = await request.form()
    kind = block.kind
    if "content" in data:
        content = str(data["content"])
        if kind == KnowledgeBlockKind.TEXT:
            block.content = sanitize_text_html(content)
        elif kind == KnowledgeBlockKind.TABLE:
            block.content = sanitize_table_json(content)
        elif kind == KnowledgeBlockKind.CODE:
            block.content = content
        elif kind == KnowledgeBlockKind.IMAGE:
            block.content = content.strip()[:500]
    if kind == KnowledgeBlockKind.CODE and "title" in data:
        block.title = str(data["title"]).strip()[:300]
    if kind == KnowledgeBlockKind.CODE and "language" in data:
        language = str(data["language"]).strip().upper()
        block.language = language if language in CODE_LANGUAGES else "TEXT"
    _touch(block.board.page)
    db.commit()
    if _is_fetch(request):
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/knowledge/pages/{block.board.page_id}", status_code=303)


@router.post("/knowledge/boards/{board_id}/blocks/reorder")
def reorder_blocks(request: Request, board_id: int, order: str = Form(""), db: Session = Depends(get_db)):
    board = db.get(KnowledgeBoard, board_id)
    if board is None:
        return _not_found(request)
    by_id = {b.id: b for b in board.blocks}
    for position, block_id in enumerate(i for i in _parse_order(order) if i in by_id):
        by_id[block_id].position = position
    _touch(board.page)
    db.commit()
    return JSONResponse({"ok": True})


@router.post("/knowledge/blocks/{block_id}/delete")
def delete_block(request: Request, block_id: int, db: Session = Depends(get_db)):
    block = db.get(KnowledgeBlock, block_id)
    if block is None:
        return _not_found(request)
    page = block.board.page
    deletion.delete_knowledge_block(db, block)
    _touch(page)
    db.commit()
    if _is_fetch(request):
        return JSONResponse({"ok": True})
    return RedirectResponse(f"/knowledge/pages/{page.id}", status_code=303)


# ── Images and files ────────────────────────────────────────────────────

@router.post("/knowledge/boards/{board_id}/upload")
async def upload_to_board(request: Request, board_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    board = db.get(KnowledgeBoard, board_id)
    if board is None:
        return _not_found(request)
    data = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB."}, status_code=413)
    original = Path(file.filename or "").name[:300] or "file"
    content_type = file.content_type or "application/octet-stream"
    extension = Path(original).suffix.lower()[:10] or mimetypes.guess_extension(content_type) or ".bin"
    is_image = content_type.startswith("image/") and extension in IMAGE_EXTENSIONS
    relative_path = f"knowledge/{board.page_id}/{uuid.uuid4().hex}{extension}"
    disk_path = screenshots_module.UPLOADS_DIR / relative_path
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(data)
    if extension == ".png":
        compress_in_background(disk_path)
    block = KnowledgeBlock(
        board_id=board.id, position=_next_block_position(board),
        kind=KnowledgeBlockKind.IMAGE if is_image else KnowledgeBlockKind.FILE,
        file_path=relative_path, file_name=original, file_size=len(data), content_type=content_type,
    )
    db.add(block)
    _touch(board.page)
    db.commit()
    db.refresh(block)
    return templates.TemplateResponse(request, "knowledge/_block_fragment.html", {"item": block})


@router.get("/knowledge/blocks/{block_id}/download")
def download_block_file(request: Request, block_id: int, db: Session = Depends(get_db)):
    block = db.get(KnowledgeBlock, block_id)
    if block is None or not block.file_path:
        return _not_found(request)
    disk_path = screenshots_module.UPLOADS_DIR / block.file_path
    if not disk_path.exists():
        return _not_found(request)
    name = block.file_name or disk_path.name
    # Starlette's own header percent-encodes a name with a space and drops the
    # plain filename=; send both (ASCII fallback + RFC 5987 form) instead.
    fallback = re.sub(r'[^ -~]|["\\]', "_", name)
    disposition = f"attachment; filename=\"{fallback}\"; filename*=utf-8''{quote(name)}"
    return FileResponse(disk_path, media_type=block.content_type or "application/octet-stream", headers={"Content-Disposition": disposition})
