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


def test_canvas_extent_is_as_wide_as_the_boards_and_has_room_below():
    # No width floor: the canvas fills the visible area in CSS, so it only
    # scrolls sideways once a board actually reaches past it.
    assert call("canvasExtent", []) == {"width": 20, "height": 900}
    assert call("canvasExtent", [box(1, 900, 800, 400, 300)]) == {"width": 1320, "height": 1500}


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


def moving(x, y, w=200, h=100):
    return {"x": x, "y": y, "w": w, "h": h}


def test_snap_move_lines_up_left_edges_and_shows_a_guide():
    assert call("snapMove", moving(104, 400), [box(1, 100, 20, 300, 300)]) == {
        "x": 100, "y": 400, "guides": [{"axis": "x", "at": 100, "from": 20, "to": 500}],
    }


def test_snap_move_leaves_a_board_further_than_the_threshold_alone():
    assert call("snapMove", moving(107, 400), [box(1, 100, 20, 300, 300)]) == {"x": 107, "y": 400, "guides": []}


def test_snap_move_lines_up_centers():
    assert call("snapMove", moving(153, 400), [box(1, 100, 20, 300, 300)]) == {
        "x": 150, "y": 400, "guides": [{"axis": "x", "at": 250, "from": 20, "to": 500}],
    }


def test_snap_move_puts_an_edge_against_another_boards_edge():
    assert call("snapMove", moving(323, 400), [box(1, 20, 20, 300, 300)])["x"] == 320


def test_snap_move_takes_the_nearest_line():
    # left edge 4 px from board 1's left, right edge 2 px from board 2's left: the 2 px wins
    result = call("snapMove", moving(104, 400), [box(1, 100, 20, 300, 300), box(2, 302, 800, 200, 100)])
    assert result["x"] == 102
    assert result["guides"] == [{"axis": "x", "at": 302, "from": 400, "to": 900}]


def test_snap_move_snaps_both_axes_independently():
    result = call("snapMove", moving(104, 23), [box(1, 100, 20, 300, 300)])
    assert (result["x"], result["y"]) == (100, 20)
    assert result["guides"] == [
        {"axis": "x", "at": 100, "from": 20, "to": 320},
        {"axis": "y", "at": 20, "from": 100, "to": 400},
    ]


def test_snap_resize_lines_up_the_right_edge_and_guides_only_the_moving_edge():
    # the left edges also line up (both at 20), but only the edge being dragged gets a guide
    assert call("snapResize", moving(20, 400, 383, 100), [box(1, 20, 20, 380, 100)], False) == {
        "w": 380, "h": 100, "guides": [{"axis": "x", "at": 400, "from": 20, "to": 500}],
    }


def test_snap_resize_snaps_the_bottom_only_while_the_height_is_resized():
    others = [box(1, 20, 20, 380, 100)]
    assert call("snapResize", moving(500, 20, 300, 97), others, True) == {
        "w": 300, "h": 100, "guides": [{"axis": "y", "at": 120, "from": 20, "to": 800}],
    }
    assert call("snapResize", moving(500, 20, 300, 97), others, False) == {"w": 300, "h": 97, "guides": []}


def test_snap_resize_never_goes_below_the_minimum_width():
    assert call("snapResize", moving(20, 400, 222, 100), [box(1, 236, 20, 300, 100)], False) == {"w": 220, "h": 100, "guides": []}


def test_snap_resize_leaves_an_edge_further_than_the_threshold_alone():
    assert call("snapResize", moving(20, 400, 387, 100), [box(1, 20, 20, 380, 100)], True)["w"] == 387


def test_snap_move_draws_one_guide_across_every_board_on_the_line():
    others = [box(1, 100, 20, 300, 100), box(2, 100, 200, 250, 100)]
    assert call("snapMove", moving(103, 500), others)["guides"] == [{"axis": "x", "at": 100, "from": 20, "to": 600}]
