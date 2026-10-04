"""app/knowledge_sanitize.py: allowlist cleaning of Knowledge Management HTML."""

import json

import pytest

from app.knowledge_sanitize import (
    EMPTY_TABLE_JSON, parse_table, sanitize_cell_html, sanitize_table_json, sanitize_text_html,
)


@pytest.mark.parametrize("raw, expected", [
    ("<script>alert(1)</script>hi", "hi"),
    ("<img src=x onerror=alert(1)>", ""),
    ('<a href="javascript:alert(1)">x</a>', '<a rel="noopener noreferrer">x</a>'),
    ('<p style="color:red" onclick="x()">t</p>', "<p>t</p>"),
    ('<a href="https://jira/NK-1" target="_blank">NK-1</a>', '<a href="https://jira/NK-1" rel="noopener noreferrer">NK-1</a>'),
    ("<h2>Title</h2><ul><li><b>a</b></li></ul>", "<h2>Title</h2><ul><li><b>a</b></li></ul>"),
    ('<span class="x">plain</span>', "plain"),
    ("<!-- c --><p>k</p>", "<p>k</p>"),
    (None, ""),
])
def test_sanitize_text_html(raw, expected):
    assert sanitize_text_html(raw) == expected


@pytest.mark.parametrize("raw, expected", [
    ("<h2>x</h2>", "x"),
    ("<b>y</b><br>z", "<b>y</b><br>z"),
    ("<div>d</div>", "d"),
    ("<script>bad()</script>ok", "ok"),
])
def test_sanitize_cell_html(raw, expected):
    assert sanitize_cell_html(raw) == expected


def test_parse_table_pads_rows_and_cleans_cells():
    raw = json.dumps({"head_row": True, "head_col": False, "rows": [["<b>a</b>", "<script>x</script>b"], ["c"]]})
    assert parse_table(raw) == {"head_row": True, "head_col": False, "rows": [["<b>a</b>", "b"], ["c", ""]]}


@pytest.mark.parametrize("raw", ["nope", "[]", '{"rows": "x"}', '{"rows": []}', '{"rows": [[]]}', None])
def test_parse_table_falls_back_to_one_empty_cell(raw):
    assert parse_table(raw) == {"head_row": False, "head_col": False, "rows": [[""]]}


def test_empty_table_is_three_by_three_with_header_row():
    data = json.loads(EMPTY_TABLE_JSON)
    assert data["head_row"] is True and data["head_col"] is False
    assert [len(r) for r in data["rows"]] == [3, 3, 3]


def test_sanitize_table_json_round_trips_a_clean_table():
    assert json.loads(sanitize_table_json(EMPTY_TABLE_JSON)) == json.loads(EMPTY_TABLE_JSON)
