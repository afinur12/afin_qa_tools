// Knowledge Management canvas (spec: "Canvas and boards"): boards drag by
// their top bar, resize from the corner, come to the front when clicked,
// push the boards below them down when they grow, maximize over the page,
// and the page itself can go full screen. Geometry saves as soon as a
// gesture ends. Pure geometry lives in knowledge_layout.js.
(function () {
  const page = document.querySelector("[data-km-page]");
  const canvas = document.querySelector("[data-km-canvas]");
  if (!page || !canvas || !page.dataset.kmPage) return;
  const L = window.KnowledgeLayout;
  const pageId = page.dataset.kmPage;
  // The page title form owns the page's save indicator (app.js resolves it
  // through the surrounding .card).
  const indicatorForm = document.querySelector("[data-km-title-form]");

  function form(fields) {
    const body = new FormData();
    Object.entries(fields).forEach(([key, value]) => body.append(key, value ?? ""));
    return body;
  }

  async function post(url, body, asJson = false) {
    setSaveState(indicatorForm, "saving");
    try {
      const response = await fetch(url, {
        method: "POST",
        headers: asJson ? { "Content-Type": "application/json", "X-Requested-With": "fetch" } : { "X-Requested-With": "fetch" },
        body: asJson ? JSON.stringify(body) : body,
      });
      setSaveState(indicatorForm, response.ok ? "saved" : "error");
      return response;
    } catch {
      setSaveState(indicatorForm, "error");
      return null;
    }
  }

  const boards = () => [...canvas.querySelectorAll(".km-board:not(.is-maximized)")];
  const boxOf = (b) => ({ id: Number(b.dataset.boardId), x: b.offsetLeft, y: b.offsetTop, w: b.offsetWidth, h: b.offsetHeight });
  const boardById = (id) => canvas.querySelector(`.km-board[data-board-id="${id}"]`);

  function growCanvas() {
    const { width, height } = L.canvasExtent(boards().map(boxOf));
    canvas.style.width = `${width}px`;
    canvas.style.minHeight = `${height}px`;
  }

  function saveGeometry(board) {
    return post(`/knowledge/boards/${board.dataset.boardId}/geometry`, form({
      x: board.offsetLeft,
      y: board.offsetTop,
      width: board.offsetWidth,
      height: board.style.height ? parseInt(board.style.height, 10) : "",
      z: parseInt(board.style.zIndex || "0", 10),
    }));
  }

  let topZ = Math.max(0, ...[...canvas.querySelectorAll(".km-board")].map((b) => parseInt(b.style.zIndex || "0", 10)));
  // Select a board; bring it to the front unless it already is. Returns
  // whether its z changed (and so needs saving).
  function select(board) {
    canvas.querySelectorAll(".km-board.is-selected").forEach((b) => b.classList.remove("is-selected"));
    board.classList.add("is-selected");
    if (parseInt(board.style.zIndex || "0", 10) >= topZ) return false;
    topZ += 1;
    board.style.zIndex = topZ;
    return true;
  }

  function track(target, pointerId, onMove, onEnd) {
    target.setPointerCapture(pointerId);
    const end = () => {
      target.removeEventListener("pointermove", onMove);
      target.removeEventListener("pointerup", end);
      target.removeEventListener("pointercancel", end);
      onEnd();
    };
    target.addEventListener("pointermove", onMove);
    target.addEventListener("pointerup", end);
    target.addEventListener("pointercancel", end);
  }

  canvas.addEventListener("pointerdown", (event) => {
    const board = event.target.closest(".km-board");
    if (!board || board.classList.contains("is-maximized") || event.button !== 0) return;
    const raised = select(board);
    const handle = event.target.closest("[data-km-resize]");
    const bar = event.target.closest("[data-km-board-bar]");
    if (handle) {
      event.preventDefault();
      const startX = event.clientX, startY = event.clientY, width = board.offsetWidth, height = board.offsetHeight;
      track(handle, event.pointerId, (move) => {
        board.style.width = `${Math.max(L.MIN_W, width + move.clientX - startX)}px`;
        // Height is only pinned once the user actually drags vertically.
        if (Math.abs(move.clientY - startY) > 2) board.style.height = `${Math.max(L.MIN_H, height + move.clientY - startY)}px`;
      }, () => { growCanvas(); saveGeometry(board); });
      return;
    }
    if (bar && !event.target.closest("button, input, form, a")) {
      event.preventDefault();
      const startX = event.clientX, startY = event.clientY, left = board.offsetLeft, top = board.offsetTop;
      track(bar, event.pointerId, (move) => {
        board.style.left = `${Math.max(0, left + move.clientX - startX)}px`;
        board.style.top = `${Math.max(0, top + move.clientY - startY)}px`;
      }, () => { growCanvas(); saveGeometry(board); });
      return;
    }
    if (raised) saveGeometry(board);
  });

  // A board that grows (typing, rows, images loading) pushes the boards
  // below it down. Dragging and page load never do.
  const lastHeight = new WeakMap();
  const observer = new ResizeObserver((entries) => {
    for (const { target } of entries) {
      const before = lastHeight.get(target);
      const now = target.offsetHeight;
      lastHeight.set(target, now);
      if (before === undefined || now <= before || target.classList.contains("is-maximized")) continue;
      const moves = L.pushDown(boards().map(boxOf), Number(target.dataset.boardId));
      moves.forEach(({ id, y }) => {
        const moved = boardById(id);
        if (moved) moved.style.top = `${y}px`;
      });
      growCanvas();
      if (moves.length) post(`/knowledge/pages/${pageId}/boards/positions`, moves, true);
    }
  });
  function watch(board) {
    lastHeight.set(board, board.offsetHeight);
    observer.observe(board);
  }
  // After knowledge_blocks.js has laid out code editors on this tick.
  setTimeout(() => canvas.querySelectorAll(".km-board").forEach(watch), 0);

  document.querySelector("[data-km-add-board]")?.addEventListener("click", async () => {
    const response = await post(`/knowledge/pages/${pageId}/boards`, form({ x: 20, y: L.nextBoardY(boards().map(boxOf)) }));
    if (!response || !response.ok) return;
    const holder = document.createElement("div");
    holder.innerHTML = (await response.text()).trim();
    const board = holder.firstElementChild;
    canvas.appendChild(board);
    topZ = Math.max(topZ, parseInt(board.style.zIndex || "0", 10));
    canvas.dispatchEvent(new CustomEvent("km:board-added", { detail: board }));
    watch(board);
    select(board);
    growCanvas();
    board.scrollIntoView({ block: "center" });
    board.querySelector("[data-km-text]")?.focus();
  });

  canvas.addEventListener("change", (event) => {
    const input = event.target.closest("[data-km-board-title]");
    if (!input) return;
    post(`/knowledge/boards/${input.closest(".km-board").dataset.boardId}/edit`, form({ title: input.value }));
  });
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches("[data-km-board-title]")) event.target.blur();
  });

  // ── maximize one board / full screen page ─────────────────────────────
  const backdrop = document.createElement("div");
  backdrop.className = "km-max-backdrop";
  backdrop.hidden = true;
  document.body.appendChild(backdrop);

  function setMaximized(board, on) {
    board.classList.toggle("is-maximized", on);
    backdrop.hidden = !on;
    const button = board.querySelector("[data-km-max]");
    if (button) button.title = on ? "Restore (Esc)" : "Maximize this board (Esc to restore)";
    if (!on) growCanvas();
  }
  canvas.addEventListener("click", (event) => {
    const button = event.target.closest("[data-km-max]");
    if (!button) return;
    const board = button.closest(".km-board");
    setMaximized(board, !board.classList.contains("is-maximized"));
  });
  backdrop.addEventListener("click", () => {
    const maximized = canvas.querySelector(".km-board.is-maximized");
    if (maximized) setMaximized(maximized, false);
  });

  const fullscreenButton = document.querySelector("[data-km-fullscreen]");
  const fullscreenLabel = fullscreenButton ? fullscreenButton.innerHTML : "";
  function setFullscreen(on) {
    page.classList.toggle("is-fullscreen", on);
    document.body.classList.toggle("km-has-fullscreen", on);
    if (fullscreenButton) fullscreenButton.innerHTML = on ? "Exit full screen (Esc)" : fullscreenLabel;
  }
  fullscreenButton?.addEventListener("click", () => setFullscreen(!page.classList.contains("is-fullscreen")));

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (document.querySelector(".modal-backdrop:not([hidden])")) return; // the open dialog closes first
    const maximized = canvas.querySelector(".km-board.is-maximized");
    if (maximized) setMaximized(maximized, false);
    else if (page.classList.contains("is-fullscreen")) setFullscreen(false);
  });

  function leaveOverlays() {
    const maximized = canvas.querySelector(".km-board.is-maximized");
    if (maximized) setMaximized(maximized, false);
    setFullscreen(false);
  }

  growCanvas();
  window.KnowledgeCanvas = { post, form, setMaximized, setFullscreen, leaveOverlays };
})();
