import json

import app.routers.api_client as api_client_module
from app.models import ApiCollection, ApiFolder, ApiRequest
from app.routers.api_client import _body_for_wire, _strip_json_line_comments


def _make_collection(db, name="Collection A"):
    collection = ApiCollection(name=name)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return collection


def _make_folder(db, collection, name="Folder A", parent=None):
    folder = ApiFolder(collection_id=collection.id, name=name, parent_folder_id=parent.id if parent else None)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


def _make_request(db, collection, name="Req A", folder=None):
    saved = ApiRequest(
        collection_id=collection.id, folder_id=folder.id if folder else None,
        name=name, method="GET", url="https://example.com",
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def test_move_request_into_folder_updates_folder_and_collection(client, db_session):
    source_collection = _make_collection(db_session, "Source")
    dest_collection = _make_collection(db_session, "Dest")
    dest_folder = _make_folder(db_session, dest_collection, "Dest Folder")
    saved = _make_request(db_session, source_collection, "My Request")

    response = client.post(
        f"/api-client/requests/{saved.id}/move",
        data={"collection_id": dest_collection.id, "folder_id": dest_folder.id},
    )
    assert response.status_code == 204

    db_session.expire_all()
    moved = db_session.get(ApiRequest, saved.id)
    assert moved.collection_id == dest_collection.id
    assert moved.folder_id == dest_folder.id


def test_move_request_to_collection_root_clears_folder(client, db_session):
    collection = _make_collection(db_session)
    folder = _make_folder(db_session, collection)
    saved = _make_request(db_session, collection, folder=folder)

    response = client.post(
        f"/api-client/requests/{saved.id}/move",
        data={"collection_id": collection.id, "folder_id": ""},
    )
    assert response.status_code == 204

    db_session.expire_all()
    moved = db_session.get(ApiRequest, saved.id)
    assert moved.folder_id is None


def test_move_request_rejects_folder_from_a_different_collection(client, db_session):
    collection_a = _make_collection(db_session, "A")
    collection_b = _make_collection(db_session, "B")
    folder_in_b = _make_folder(db_session, collection_b)
    saved = _make_request(db_session, collection_a)

    response = client.post(
        f"/api-client/requests/{saved.id}/move",
        data={"collection_id": collection_a.id, "folder_id": folder_in_b.id},
    )
    assert response.status_code == 404


def test_move_request_returns_404_for_unknown_request(client, db_session):
    collection = _make_collection(db_session)
    response = client.post(
        "/api-client/requests/999999/move",
        data={"collection_id": collection.id, "folder_id": ""},
    )
    assert response.status_code == 404


def test_strip_json_line_comments_removes_commented_lines():
    body = '{\n  "a": 1,\n  // "b": 2,\n  "c": 3\n}'
    result = json.loads(_strip_json_line_comments(body))
    assert result == {"a": 1, "c": 3}


def test_strip_json_line_comments_drops_dangling_trailing_comma():
    # The commented-out line is the last array item — naively deleting it
    # would leave a trailing comma before the closing bracket.
    body = '{\n  "attrs": [\n    "A",\n    // "B"\n  ]\n}'
    result = json.loads(_strip_json_line_comments(body))
    assert result == {"attrs": ["A"]}


def test_strip_json_line_comments_preserves_slashes_inside_strings():
    body = '{\n  // "excluded": 1,\n  "url": "https://example.com/a//b"\n}'
    result = json.loads(_strip_json_line_comments(body))
    assert result == {"url": "https://example.com/a//b"}


def test_body_for_wire_leaves_already_valid_json_untouched():
    body = '{"url": "https://example.com"}'
    assert _body_for_wire(body) == body


def test_body_for_wire_leaves_non_json_untouched():
    body = "<note>// not a comment</note>"
    assert _body_for_wire(body) == body


def test_body_for_wire_leaves_body_alone_if_stripping_still_invalid():
    body = "not json at all // still not json"
    assert _body_for_wire(body) == body


def test_body_for_wire_handles_empty_body():
    assert _body_for_wire("") == ""
    assert _body_for_wire(None) == ""


def test_send_disables_tls_verification(client, monkeypatch):
    # Every target this proxies to is an internal SIT/dev host over VPN,
    # almost always on a self-signed or internal-CA certificate — asserts
    # the fix for "CERTIFICATE_VERIFY_FAILED: self-signed certificate"
    # actually reaches the httpx client, without hitting real network or
    # needing a real certificate to test against.
    captured_kwargs = {}

    class FakeResponse:
        status_code = 200
        text = "{}"
        content = b"{}"
        headers = {}

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured_kwargs.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def request(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(api_client_module.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/api-client/send",
        json={"method": "GET", "url": "https://internal-sit.example.com", "headers": [], "body": "", "collection_id": None},
    )
    assert response.status_code == 200
    assert captured_kwargs.get("verify") is False


def test_resolve_endpoint_strips_comments_from_curl_preview(client):
    body = '{\n  "attributes": [\n    "A",\n    // "B",\n    "C"\n  ]\n}'
    response = client.post(
        "/api-client/resolve",
        json={"method": "POST", "url": "https://example.com", "headers": [], "body": body, "collection_id": None},
    )
    assert response.status_code == 200
    curl = response.json()["curl"]
    assert "// " not in curl
    assert '"A"' in curl and '"C"' in curl and '"B"' not in curl
