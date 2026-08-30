import json

from app.routers.api_client import _body_for_wire, _strip_json_line_comments


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
