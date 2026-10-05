// Pure geometry for the Knowledge Management canvas — no DOM, so it runs
// under Node in tests/test_knowledge_layout_js.py. A "box" is
// {id, x, y, w, h} in canvas pixels.
(function (root) {
  const GAP = 20; // kept between a board that grew and the boards it pushes
  const NEW_BOARD_GAP = 24; // above a newly added board
  const MIN_W = 220;
  const MIN_H = 80;

  const overlapsX = (a, b) => a.x < b.x + b.w && b.x < a.x + a.w;

  // A board grew: every board that overlaps it horizontally, starts at or
  // below its top, and starts above its new bottom + GAP moves down to
  // bottom + GAP — cascading to the boards those push. Returns [{id, y}]
  // for every board that moved.
  function pushDown(boxes, grownId) {
    const items = boxes.map((b) => ({ ...b })).sort((a, b) => a.y - b.y || a.id - b.id);
    const originalY = new Map(boxes.map((b) => [b.id, b.y]));
    const moved = new Set([grownId]);
    for (const upper of items) {
      if (!moved.has(upper.id)) continue;
      const bottom = upper.y + upper.h;
      for (const lower of items) {
        if (lower.id === upper.id || originalY.get(lower.id) < originalY.get(upper.id) || !overlapsX(upper, lower)) continue;
        if (lower.y < bottom + GAP) {
          lower.y = bottom + GAP;
          moved.add(lower.id);
        }
      }
    }
    return items.filter((b) => b.y !== originalY.get(b.id)).map((b) => ({ id: b.id, y: b.y }));
  }

  function nextBoardY(boxes) {
    return boxes.length ? Math.max(...boxes.map((b) => b.y + b.h)) + NEW_BOARD_GAP : 20;
  }

  // Canvas size: just wide enough for its boards (the canvas also fills the
  // visible area in CSS, so it only scrolls sideways once a board reaches
  // past it), and tall enough for its boards plus 400px of room below.
  function canvasExtent(boxes) {
    const right = boxes.length ? Math.max(...boxes.map((b) => b.x + b.w)) : 0;
    const bottom = boxes.length ? Math.max(...boxes.map((b) => b.y + b.h)) : 0;
    return { width: right + GAP, height: Math.max(900, bottom + 400) };
  }

  // PDF page break: the lowest y in (from + 60% of the slice, limit] that
  // sits in a gap between boards (16px clear of an edge); otherwise limit.
  function bestCut(from, limit, spans) {
    const floor = from + (limit - from) * 0.6;
    const free = spans
      .flatMap(([top, bottom]) => [top - 16, bottom + 16])
      .filter((y) => y > floor && y <= limit && !spans.some(([top, bottom]) => y > top && y < bottom))
      .sort((a, b) => b - a);
    return free.length ? free[0] : limit;
  }

  // ── snapping to other boards ──────────────────────────────────────────
  // A board's lines: left / center / right (x), top / middle / bottom (y).
  // A guide {axis: "x", at, from, to} is a vertical line at x = at from
  // y = from to y = to, spanning every board on it; axis "y" is the
  // horizontal one.
  const SNAP = 6;
  const linesX = (b) => [b.x, b.x + b.w / 2, b.x + b.w];
  const linesY = (b) => [b.y, b.y + b.h / 2, b.y + b.h];

  // The smallest move (within threshold) that puts one of `own` on one of
  // `theirs`; 0 when nothing is that close.
  function nearestSnap(own, theirs, threshold) {
    let best = 0;
    let found = false;
    for (const line of own) {
      for (const target of theirs) {
        const delta = target - line;
        if (Math.abs(delta) <= threshold && (!found || Math.abs(delta) < Math.abs(best))) {
          best = delta;
          found = true;
        }
      }
    }
    return best;
  }

  // Guides for each of `own` (lines of `placed`) that lines up with a line
  // of another board.
  function guidesFor(axis, own, placed, others) {
    const linesOf = axis === "x" ? linesX : linesY;
    const startOf = axis === "x" ? (b) => b.y : (b) => b.x;
    const endOf = axis === "x" ? (b) => b.y + b.h : (b) => b.x + b.w;
    const onLine = new Map(); // guide position -> boxes on it
    for (const line of own) {
      for (const other of others) {
        const hit = linesOf(other).find((target) => Math.abs(target - line) <= 1);
        if (hit === undefined) continue;
        const at = Math.round(hit);
        if (!onLine.has(at)) onLine.set(at, [placed]);
        onLine.get(at).push(other);
      }
    }
    return [...onLine]
      .sort(([a], [b]) => a - b)
      .map(([at, boxes]) => ({ axis, at, from: Math.min(...boxes.map(startOf)), to: Math.max(...boxes.map(endOf)) }));
  }

  // A board dragged to (moving.x, moving.y) snaps, each axis on its own, to
  // the nearest line of another board within `threshold` px — any of its
  // three lines to any of theirs. Returns the snapped {x, y} and a guide for
  // every line the result lines up with.
  function snapMove(moving, others, threshold = SNAP) {
    const placed = {
      ...moving,
      x: Math.round(moving.x + nearestSnap(linesX(moving), others.flatMap(linesX), threshold)),
      y: Math.round(moving.y + nearestSnap(linesY(moving), others.flatMap(linesY), threshold)),
    };
    const guides = [
      ...guidesFor("x", linesX(placed), placed, others),
      ...guidesFor("y", linesY(placed), placed, others),
    ];
    return { x: placed.x, y: placed.y, guides };
  }

  // A board resized from its corner to (box.w, box.h): its right edge snaps
  // to the nearest line of another board, and — when `bottom` is set (the
  // height is being resized too) — its bottom edge as well, never below
  // MIN_W / MIN_H. Returns {w, h} and guides for the dragged edges only.
  function snapResize(box, others, bottom, threshold = SNAP) {
    const right = box.x + box.w;
    const w = Math.max(MIN_W, Math.round(box.w + nearestSnap([right], others.flatMap(linesX), threshold)));
    const h = bottom
      ? Math.max(MIN_H, Math.round(box.h + nearestSnap([box.y + box.h], others.flatMap(linesY), threshold)))
      : box.h;
    const placed = { ...box, w, h };
    const guides = [
      ...guidesFor("x", [placed.x + w], placed, others),
      ...(bottom ? guidesFor("y", [placed.y + h], placed, others) : []),
    ];
    return { w, h, guides };
  }

  // Tab-separated text (copied from Excel / OneNote) -> rows of cell strings.
  function tsvToGrid(text) {
    const lines = String(text).replace(/\r/g, "").split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
    return lines.map((line) => line.split("\t"));
  }

  const api = { GAP, NEW_BOARD_GAP, MIN_W, MIN_H, SNAP, pushDown, nextBoardY, canvasExtent, bestCut, snapMove, snapResize, tsvToGrid };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KnowledgeLayout = api;
})(typeof window !== "undefined" ? window : globalThis);
