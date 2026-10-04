"""knowledge_layout.js pure geometry, executed under Node (skipped without node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

LAYOUT = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "knowledge_layout.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


def call(fn, *args):
    script = (
        f"const L = require({json.dumps(str(LAYOUT))});"
        f"process.stdout.write(JSON.stringify(L.{fn}(...{json.dumps(list(args))})));"
    )
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def box(id, x, y, w, h):
    return {"id": id, "x": x, "y": y, "w": w, "h": h}


def test_push_down_moves_an_overlapped_board_below_the_grown_one():
    assert call("pushDown", [box(1, 20, 20, 500, 600), box(2, 20, 470, 480, 300)], 1) == [{"id": 2, "y": 640}]


def test_push_down_ignores_boards_beside_it():
    assert call("pushDown", [box(1, 20, 20, 500, 600), box(2, 560, 300, 320, 200)], 1) == []


def test_push_down_cascades():
    boxes = [box(1, 20, 20, 300, 300), box(2, 20, 300, 300, 100), box(3, 20, 410, 300, 100)]
    assert call("pushDown", boxes, 1) == [{"id": 2, "y": 340}, {"id": 3, "y": 460}]


def test_push_down_leaves_a_board_with_enough_gap_alone():
    assert call("pushDown", [box(1, 20, 20, 300, 300), box(2, 20, 400, 300, 100)], 1) == []


def test_push_down_never_moves_boards_above():
    assert call("pushDown", [box(1, 20, 300, 300, 300), box(2, 20, 20, 300, 400)], 1) == []


def test_next_board_y():
    assert call("nextBoardY", []) == 20
    assert call("nextBoardY", [box(1, 20, 20, 300, 300), box(2, 400, 100, 100, 500)]) == 624


def test_canvas_extent_has_a_floor_and_room_to_grow():
    assert call("canvasExtent", []) == {"width": 1200, "height": 900}
    assert call("canvasExtent", [box(1, 900, 800, 400, 300)]) == {"width": 1700, "height": 1500}


def test_best_cut_prefers_the_lowest_gap_between_boards():
    assert call("bestCut", 0, 700, [[0, 500], [540, 900]]) == 524


def test_best_cut_falls_back_to_the_limit():
    assert call("bestCut", 0, 700, [[0, 2000]]) == 700


def test_push_down_cascades_through_a_staggered_layout():
    # B is pushed below the grown board G; D sits beside G but under B, so it must move too.
    boxes = [box(1, 20, 20, 300, 1000), box(2, 200, 100, 300, 50), box(3, 400, 500, 300, 700)]
    assert call("pushDown", boxes, 1) == [{"id": 2, "y": 1040}, {"id": 3, "y": 1110}]


def test_best_cut_ignores_gaps_in_the_top_sixty_percent():
    assert call("bestCut", 0, 700, [[0, 200], [240, 2000]]) == 700


def test_best_cut_skips_candidates_inside_another_board():
    assert call("bestCut", 0, 700, [[0, 450], [490, 560], [600, 2000]]) == 584


def test_best_cut_needs_a_gap_wider_than_the_margin():
    assert call("bestCut", 0, 700, [[0, 500], [510, 2000]]) == 700


def test_tsv_to_grid():
    assert call("tsvToGrid", "Owner\tAndri\nReviewer\tPutu\n") == [["Owner", "Andri"], ["Reviewer", "Putu"]]
    assert call("tsvToGrid", "a\r\nb") == [["a"], ["b"]]
