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

  // Canvas size: every board plus 400px of room beyond, never below the floor.
  function canvasExtent(boxes) {
    const right = boxes.length ? Math.max(...boxes.map((b) => b.x + b.w)) : 0;
    const bottom = boxes.length ? Math.max(...boxes.map((b) => b.y + b.h)) : 0;
    return { width: Math.max(1200, right + 400), height: Math.max(900, bottom + 400) };
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

  // Tab-separated text (copied from Excel / OneNote) -> rows of cell strings.
  function tsvToGrid(text) {
    const lines = String(text).replace(/\r/g, "").split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
    return lines.map((line) => line.split("\t"));
  }

  const api = { GAP, NEW_BOARD_GAP, MIN_W, MIN_H, pushDown, nextBoardY, canvasExtent, bestCut, tsvToGrid };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.KnowledgeLayout = api;
})(typeof window !== "undefined" ? window : globalThis);
