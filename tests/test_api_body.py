"""app/api_body.py: request body modes (raw / urlencoded / form-data)."""

import json

import app.routers.api_client as api_client_module
from app.api_body import (
    encode_multipart, encode_urlencoded, enabled_pairs, parse_form_rows,
    urlencoded_text_to_rows, with_content_type,
)
from app.curl_tools import build_curl, parse_curl
from app.models import ApiCollection, ApiRequest, ApiVariable, ApiVariableScope


def _rows(*pairs, disabled=()):
    return json.dumps([
        {"key": k, "value": v, "description": "", "enabled": k not in disabled} for k, v in pairs
    ])


# ── Pure helpers ────────────────────────────────────────────────────────

def test_parse_form_rows_tolerates_garbage():
    assert parse_form_rows("") == []
    assert parse_form_rows("not json") == []
    assert parse_form_rows('{"a": 1}') == []


def test_parse_form_rows_fills_defaults():
    rows = parse_form_rows('[{"key": "a", "value": "1"}]')
    assert rows == [{"key": "a", "value": "1", "description": "", "enabled": True}]


def test_enabled_pairs_skips_disabled_and_blank_keys():
    rows = parse_form_rows(_rows(("a", "1"), ("b", "2"), ("", "x"), disabled=("b",)))
    assert enabled_pairs(rows) == [("a", "1")]


def test_encode_urlencoded_encodes_values_form_style():
    assert encode_urlencoded([("scope", "openid profile"), ("login", "tel:+62&x")]) == \
        "scope=openid+profile&login=tel%3A%2B62%26x"


def test_encode_multipart_text_fields():
    content, content_type = encode_multipart([("a", "1"), ('we"ird', "two\nlines")], boundary="BOUND")
    assert content_type == "multipart/form-data; boundary=BOUND"
    assert content == (
        b'--BOUND\r\nContent-Disposition: form-data; name="a"\r\n\r\n1\r\n'
        b'--BOUND\r\nContent-Disposition: form-data; name="we%22ird"\r\n\r\ntwo\nlines\r\n'
        b"--BOUND--\r\n"
    )


def test_with_content_type_keeps_user_header_unless_replacing():
    headers = [["content-type", "application/vnd.api+json"]]
    assert with_content_type(headers, "application/json") == headers
    assert with_content_type(headers, "multipart/form-data; boundary=X", replace=True) == [
        ["Content-Type", "multipart/form-data; boundary=X"]
    ]
    assert with_content_type([], "text/plain") == [["Content-Type", "text/plain"]]


def test_urlencoded_text_to_rows_decodes_form_style():
    rows = urlencoded_text_to_rows("scope=openid+profile&login=tel%3A62&flag")
    assert [(r["key"], r["value"]) for r in rows] == [("scope", "openid profile"), ("login", "tel:62"), ("flag", "")]
    assert all(r["enabled"] for r in rows)


# ── curl ────────────────────────────────────────────────────────────────

def test_build_curl_urlencoded_and_multipart():
    curl = build_curl("POST", "https://x", [], "", urlencoded=[("a", "1 2")])
    assert "--data-urlencode 'a=1 2'" in curl
    curl = build_curl("POST", "https://x", [], "", multipart=[("a", "@notafile")])
    assert "--form-string a=@notafile" in curl


def test_parse_curl_form_flags_become_formdata_rows():
    result = parse_curl("curl https://x -F 'a=1' --form-string 'b=@2'")
    assert result["method"] == "POST"
    assert result["body_mode"] == "formdata"
    assert [(r["key"], r["value"]) for r in json.loads(result["body"])] == [("a", "1"), ("b", "@2")]


def test_parse_curl_route_turns_urlencoded_body_into_rows(client):
    resp = client.post("/api-client/parse-curl", json={
        "text": "curl https://x -H 'Content-Type: application/x-www-form-urlencoded' -d 'scope=openid+x&login=tel%3A62'",
    })
    data = resp.json()
    assert data["body_mode"] == "urlencoded"
    assert [(r["key"], r["value"]) for r in json.loads(data["body"])] == [("scope", "openid x"), ("login", "tel:62")]


# ── Send / resolve ──────────────────────────────────────────────────────

def _capture_send(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        text = "{}"
        content = b"{}"
        headers = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, method, url, **kwargs):
            captured.update(kwargs, method=method, url=url)
            return FakeResponse()

    monkeypatch.setattr(api_client_module.httpx, "AsyncClient", FakeAsyncClient)
    return captured


def test_send_urlencoded_resolves_vars_per_field_and_sets_content_type(client, db_session, monkeypatch):
    db_session.add(ApiVariable(scope=ApiVariableScope.GLOBAL, key="phone", value="+62 811&1"))
    db_session.commit()
    captured = _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "POST", "url": "https://x", "headers": [], "collection_id": None,
        "body_mode": "urlencoded", "body": _rows(("login", "tel:{{phone}}"), ("skip", "me"), disabled=("skip",)),
    })
    assert captured["content"] == b"login=tel%3A%2B62+811%261"
    assert captured["headers"]["Content-Type"] == "application/x-www-form-urlencoded"


def test_send_formdata_builds_multipart_and_overrides_content_type(client, monkeypatch):
    captured = _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "POST", "url": "https://x", "collection_id": None,
        "headers": [["Content-Type", "multipart/form-data"]],
        "body_mode": "formdata", "body": _rows(("a", "1")),
    })
    content_type = captured["headers"]["Content-Type"]
    assert content_type.startswith("multipart/form-data; boundary=")
    boundary = content_type.split("boundary=")[1]
    assert captured["content"] == f'--{boundary}\r\nContent-Disposition: form-data; name="a"\r\n\r\n1\r\n--{boundary}--\r\n'.encode()


def test_send_raw_modes_add_content_type_only_when_body_present(client, monkeypatch):
    captured = _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "POST", "url": "https://x", "headers": [], "collection_id": None,
        "body_mode": "xml", "body": "<a/>",
    })
    assert captured["headers"]["Content-Type"] == "application/xml"
    assert captured["content"] == b"<a/>"

    client.post("/api-client/send", json={
        "method": "GET", "url": "https://x", "headers": [], "collection_id": None,
        "body_mode": "json", "body": "",
    })
    assert "Content-Type" not in captured["headers"]
    assert captured["content"] is None


def test_send_none_mode_sends_no_body(client, monkeypatch):
    captured = _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "POST", "url": "https://x", "headers": [], "collection_id": None,
        "body_mode": "none", "body": "leftover draft",
    })
    assert captured["content"] is None


def test_send_legacy_payload_without_mode_is_sent_verbatim(client, monkeypatch):
    captured = _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "POST", "url": "https://x", "headers": [], "collection_id": None, "body": "a=1",
    })
    assert captured["content"] == b"a=1"
    assert "Content-Type" not in captured["headers"]


def test_send_records_body_mode_in_history(client, db_session, monkeypatch):
    from app.models import ApiHistory

    _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "POST", "url": "https://x", "headers": [], "collection_id": None,
        "body_mode": "urlencoded", "body": _rows(("a", "1")),
    })
    hist = db_session.query(ApiHistory).order_by(ApiHistory.id.desc()).first()
    assert hist.request_body_mode == "urlencoded"
    assert [(r["key"], r["value"]) for r in json.loads(hist.request_body)] == [("a", "1")]


def test_send_url_keeps_variables_and_encodes_spaces_on_the_wire(client, db_session, monkeypatch):
    db_session.add(ApiVariable(scope=ApiVariableScope.GLOBAL, key="guid", value="abc-123"))
    db_session.commit()
    captured = _capture_send(monkeypatch)
    client.post("/api-client/send", json={
        "method": "GET", "url": "https://x/p?id={{guid}}&q=a b$", "headers": [], "collection_id": None,
        "body_mode": "none", "body": "",
    })
    assert captured["url"] == "https://x/p?id=abc-123&q=a%20b$"


def test_resolve_curl_preview_for_formdata_omits_content_type(client):
    resp = client.post("/api-client/resolve", json={
        "method": "POST", "url": "https://x", "headers": [], "collection_id": None,
        "body_mode": "formdata", "body": _rows(("a", "1")),
    })
    curl = resp.json()["curl"]
    assert "--form-string a=1" in curl
    assert "Content-Type" not in curl


# ── Save / builder / history restore ────────────────────────────────────

def _collection(db):
    c = ApiCollection(name="C")
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


def test_create_and_edit_request_store_body_mode(client, db_session):
    c = _collection(db_session)
    client.post("/api-client/requests", data={
        "collection_id": c.id, "name": "R", "body_mode": "urlencoded", "body": _rows(("a", "1")),
    })
    saved = db_session.query(ApiRequest).filter_by(name="R").one()
    assert saved.body_mode == "urlencoded"
    client.post(f"/api-client/requests/{saved.id}/edit", data={"name": "R", "body_mode": "text", "body": "hi"})
    db_session.refresh(saved)
    assert (saved.body_mode, saved.body) == ("text", "hi")


def test_builder_exposes_body_mode_to_the_page(client, db_session):
    c = _collection(db_session)
    saved = ApiRequest(collection_id=c.id, name="R", method="POST", url="https://x", body_mode="formdata", body=_rows(("a", "1")))
    db_session.add(saved)
    db_session.commit()
    page = client.get(f"/api-client?request_id={saved.id}").text
    assert '"body_mode": "formdata"' in page
    assert "data-ac-body-mode" in page


# ── Postman ─────────────────────────────────────────────────────────────

def test_postman_import_keeps_urlencoded_and_formdata_rows(client, db_session):
    collection = {
        "info": {"name": "PM", "schema": "x"},
        "item": [
            {"name": "U", "request": {"method": "POST", "url": "https://x", "body": {
                "mode": "urlencoded", "urlencoded": [
                    {"key": "a", "value": "1", "description": "first"},
                    {"key": "b", "value": "2", "disabled": True},
                ]}}},
            {"name": "F", "request": {"method": "POST", "url": "https://x", "body": {
                "mode": "formdata", "formdata": [
                    {"key": "t", "value": "v", "type": "text"},
                    {"key": "f", "src": "/tmp/x", "type": "file"},
                ]}}},
            {"name": "X", "request": {"method": "POST", "url": "https://x", "body": {
                "mode": "raw", "raw": "<a/>", "options": {"raw": {"language": "xml"}}}}},
        ],
    }
    client.post("/api-client/collections/import", files={"file": ("c.json", json.dumps(collection), "application/json")})
    by_name = {r.name: r for r in db_session.query(ApiRequest).all()}
    assert by_name["U"].body_mode == "urlencoded"
    assert json.loads(by_name["U"].body) == [
        {"key": "a", "value": "1", "description": "first", "enabled": True},
        {"key": "b", "value": "2", "description": "", "enabled": False},
    ]
    assert by_name["F"].body_mode == "formdata"
    assert [r["key"] for r in json.loads(by_name["F"].body)] == ["t"]
    assert (by_name["X"].body_mode, by_name["X"].body) == ("xml", "<a/>")


def test_postman_export_writes_matching_body_mode(client, db_session):
    c = _collection(db_session)
    db_session.add_all([
        ApiRequest(collection_id=c.id, name="U", url="https://x", body_mode="urlencoded", body=_rows(("a", "1"), ("b", "2"), disabled=("b",))),
        ApiRequest(collection_id=c.id, name="T", url="https://x", body_mode="text", body="hi"),
    ])
    db_session.commit()
    data = client.get(f"/api-client/collections/{c.id}/export").json()
    items = {i["name"]: i["request"]["body"] for i in data["item"]}
    assert items["U"] == {"mode": "urlencoded", "urlencoded": [
        {"key": "a", "value": "1", "description": "", "type": "text"},
        {"key": "b", "value": "2", "description": "", "type": "text", "disabled": True},
    ]}
    assert items["T"] == {"mode": "raw", "raw": "hi", "options": {"raw": {"language": "text"}}}


def test_history_detail_shows_form_rows_as_fields(client, db_session):
    from app.models import ApiHistory

    hist = ApiHistory(method="POST", url="https://x", request_body_mode="urlencoded",
                      request_body=_rows(("scope", "openid"), ("off", "x"), disabled=("off",)))
    db_session.add(hist)
    db_session.commit()
    page = client.get(f"/api-client/history/{hist.id}").text
    assert "x-www-form-urlencoded" in page
    assert "scope" in page and "openid" in page
    assert '"key"' not in page  # not the raw JSON rows
