import json
import shlex

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import CurlAttachType, CurlCollection

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")


def parse_curl(raw_text: str) -> dict:
    try:
        tokens = shlex.split(raw_text.strip())
    except ValueError:
        tokens = raw_text.strip().split()

    method = "GET"
    url = ""
    headers: dict[str, str] = {}
    body = ""

    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "curl":
            i += 1
        elif tok in ("-X", "--request") and i + 1 < len(tokens):
            method = tokens[i + 1].upper()
            i += 2
        elif tok in ("-H", "--header") and i + 1 < len(tokens):
            key, _, value = tokens[i + 1].partition(":")
            if value:
                headers[key.strip()] = value.strip()
            i += 2
        elif tok in ("-d", "--data", "--data-raw", "--data-binary") and i + 1 < len(tokens):
            body = tokens[i + 1]
            if method == "GET":
                method = "POST"
            i += 2
        elif tok.startswith("-"):
            i += 1
        else:
            if not url:
                url = tok
            i += 1

    return {"method": method, "url": url, "headers": json.dumps(headers), "body": body}


def _redirect_target(attach_type: CurlAttachType, attach_id: int) -> str:
    if attach_type == CurlAttachType.STORY:
        return f"/stories/{attach_id}"
    return f"/subtasks/{attach_id}"


@router.post("/curls")
def create_curl(
    request: Request,
    attach_type: str = Form(...),
    attach_id: int = Form(...),
    raw_text: str = Form(...),
    db: Session = Depends(get_db),
):
    attach_type_enum = CurlAttachType(attach_type)
    parsed = parse_curl(raw_text)
    db.add(
        CurlCollection(
            attach_type=attach_type_enum, attach_id=attach_id, raw_text=raw_text,
            method=parsed["method"], url=parsed["url"], headers=parsed["headers"], body=parsed["body"],
        )
    )
    db.commit()
    return RedirectResponse(url=_redirect_target(attach_type_enum, attach_id), status_code=303)


@router.post("/curls/{curl_id}/delete")
def delete_curl(
    request: Request,
    curl_id: int,
    attach_type: str = Form(...),
    attach_id: int = Form(...),
    db: Session = Depends(get_db),
):
    curl = db.get(CurlCollection, curl_id)
    if curl is not None:
        db.delete(curl)
        db.commit()
    return RedirectResponse(url=_redirect_target(CurlAttachType(attach_type), attach_id), status_code=303)
