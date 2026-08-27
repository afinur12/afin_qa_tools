from fastapi import APIRouter, Request

from app.templating import templates

router = APIRouter(prefix="/utility")

# Every tool runs client-side (no server round trip), so each route just
# renders a static shell; the page's own JS does the work. Order here sets
# the order tools appear in on the index grid.
TOOLS = [
    {"slug": "uuid", "name": "UUID Generator", "icon": "icon_hash",
     "desc": "Generate v4 UUIDs in bulk, with optional uppercase and no-hyphen formatting."},
    {"slug": "json-formatter", "name": "JSON Formatter", "icon": "icon_braces",
     "desc": "Prettify, minify, and validate JSON with inline error messages."},
    {"slug": "text-diff", "name": "Text Diff Checker", "icon": "icon_diff",
     "desc": "Compare two blocks of text line-by-line or word-by-word."},
    {"slug": "jmespath", "name": "JMESPath Playground", "icon": "icon_search",
     "desc": "Query JSON with JMESPath expressions and see the result live."},
    {"slug": "date-converter", "name": "Date-Time Converter", "icon": "icon_calendar",
     "desc": "Convert between Unix timestamps, ISO 8601, and human-readable dates."},
    {"slug": "sql-formatter", "name": "SQL Formatter", "icon": "icon_database",
     "desc": "Pretty-print SQL across several dialects with configurable casing."},
    {"slug": "qr-code", "name": "QR Code Generator", "icon": "icon_qrcode",
     "desc": "Turn any text or URL into a downloadable QR code."},
    {"slug": "pdf-tools", "name": "PDF Tools", "icon": "icon_doc",
     "desc": "Merge, split, and rotate PDF files without leaving the browser."},
]
TOOLS_BY_SLUG = {t["slug"]: t for t in TOOLS}


@router.get("/")
def index(request: Request):
    return templates.TemplateResponse(request, "utility/index.html", {"tools": TOOLS})


@router.get("/uuid")
def uuid_tool(request: Request):
    return templates.TemplateResponse(request, "utility/uuid.html", {"tool": TOOLS_BY_SLUG["uuid"]})


@router.get("/json-formatter")
def json_formatter(request: Request):
    return templates.TemplateResponse(request, "utility/json_formatter.html", {"tool": TOOLS_BY_SLUG["json-formatter"]})


@router.get("/text-diff")
def text_diff(request: Request):
    return templates.TemplateResponse(request, "utility/text_diff.html", {"tool": TOOLS_BY_SLUG["text-diff"]})


@router.get("/jmespath")
def jmespath_tool(request: Request):
    return templates.TemplateResponse(request, "utility/jmespath.html", {"tool": TOOLS_BY_SLUG["jmespath"]})


@router.get("/date-converter")
def date_converter(request: Request):
    return templates.TemplateResponse(request, "utility/date_converter.html", {"tool": TOOLS_BY_SLUG["date-converter"]})


@router.get("/sql-formatter")
def sql_formatter(request: Request):
    return templates.TemplateResponse(request, "utility/sql_formatter.html", {"tool": TOOLS_BY_SLUG["sql-formatter"]})


@router.get("/qr-code")
def qr_code(request: Request):
    return templates.TemplateResponse(request, "utility/qr_code.html", {"tool": TOOLS_BY_SLUG["qr-code"]})


@router.get("/pdf-tools")
def pdf_tools(request: Request):
    return templates.TemplateResponse(request, "utility/pdf_tools.html", {"tool": TOOLS_BY_SLUG["pdf-tools"]})
