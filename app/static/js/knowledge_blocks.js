// Knowledge Management blocks (spec: "Blocks"): the + Add menu, text blocks
// with a floating format toolbar, code blocks on the app's shared code
// editor (wrap mode) and move up / down. Content saves through app.js's
// generic [data-autosave] forms; board requests go through
// window.KnowledgeCanvas.post (knowledge_canvas.js, loaded first).
(function () {
  const canvas = document.querySelector("[data-km-canvas]");
  if (!canvas || !window.KnowledgeCanvas) return;
  const { post, form } = window.KnowledgeCanvas;

  // ── wiring for blocks rendered by the server or inserted later ────────
  function wireText(editor) {
    if (editor.dataset.kmWired) return;
    editor.dataset.kmWired = "1";
    const hidden = editor.closest("form").querySelector("[data-km-text-value]");
    // Runs before the "input" event bubbles on to the form's autosave
    // listener, so the debounced save always posts the latest HTML.
    editor.addEventListener("input", () => {
      hidden.value = editor.innerHTML;
    });
  }

  function wireCode(textarea) {
    if (textarea.dataset.kmWired) return;
    textarea.dataset.kmWired = "1";
    const codeForm = textarea.closest("form");
    const languageField = codeForm.querySelector("[data-note-language]");
    const label = codeForm.querySelector("[data-km-code-lang]");
    const language = () => detectSnippetLanguage(textarea.value) || "TEXT";
    attachCodeEditor(textarea, () => HLJS_LANGUAGE_MAP[language()] || "plaintext", {
      wrap: true,
      onSync: () => {
        languageField.value = language();
        if (label) label.textContent = language();
      },
    });
  }

  // ── tables: cells are contenteditable; the whole grid saves as JSON ────
  let lastCell = null;
  const L = window.KnowledgeLayout;
  const tableOf = (tableForm) => tableForm.querySelector("table");
  // Dragged column widths live on <col>s and are all or nothing (see the
  // table macro): once set, the table is laid out fixed at their total.
  const DEFAULT_COL_WIDTH = 120;
  const colsOf = (table) => [...table.querySelectorAll(":scope > colgroup > col")];
  function newCol(width = DEFAULT_COL_WIDTH) {
    const col = document.createElement("col");
    col.style.width = `${width}px`;
    return col;
  }
  function fitWidth(table) {
    const cols = colsOf(table);
    table.style.width = cols.length ? `${cols.reduce((sum, col) => sum + parseInt(col.style.width, 10), 0)}px` : "";
  }
  function addColumnAtEnd(table) {
    [...table.rows].forEach((tr) => tr.appendChild(newCell()));
    table.querySelector(":scope > colgroup")?.appendChild(newCol());
  }
  function serializeTable(tableForm) {
    const table = tableOf(tableForm);
    const data = {
      head_row: table.classList.contains("has-head-row"),
      head_col: table.classList.contains("has-head-col"),
      rows: [...table.rows].map((tr) => [...tr.cells].map((td) => td.innerHTML)),
    };
    const cols = colsOf(table);
    if (cols.length) data.col_widths = cols.map((col) => parseInt(col.style.width, 10) || null);
    const heights = [...table.rows].map((tr) => parseInt(tr.style.height, 10) || null);
    if (heights.some(Boolean)) data.row_heights = heights;
    tableForm.querySelector("[data-km-table-value]").value = JSON.stringify(data);
  }
  // Structural edits fire no native "input" event — announce one so the
  // form's autosave picks them up.
  function tableChanged(tableForm) {
    serializeTable(tableForm);
    tableForm.querySelector("[data-km-table-value]").dispatchEvent(new Event("input", { bubbles: true }));
  }
  function newCell() {
    const td = document.createElement("td");
    td.contentEditable = "true";
    return td;
  }
  function addRow(table, afterRow) {
    const tr = document.createElement("tr");
    for (let i = 0; i < table.rows[0].cells.length; i++) tr.appendChild(newCell());
    if (afterRow) afterRow.after(tr);
    else table.tBodies[0].appendChild(tr);
    return tr;
  }

  function wireTable(tableForm) {
    if (tableForm.dataset.kmWired) return;
    tableForm.dataset.kmWired = "1";
    tableForm.addEventListener("input", (event) => {
      if (event.target.matches("td")) serializeTable(tableForm);
    });
    tableForm.addEventListener("focusin", (event) => {
      if (event.target.matches("td")) lastCell = event.target;
    });
    tableForm.addEventListener("change", (event) => {
      const box = event.target.closest("input[data-km-tbl]");
      if (!box) return;
      tableOf(tableForm).classList.toggle(box.dataset.kmTbl === "head-row" ? "has-head-row" : "has-head-col", box.checked);
      tableChanged(tableForm);
    });
    // The floating tools never take focus: a cell being edited stays focused
    // (+ Row / − Col act on it), and the bar hides once the pointer leaves.
    tableForm.addEventListener("mousedown", (event) => {
      if (event.target.closest(".km-table-tools")) event.preventDefault();
    });
    tableForm.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-km-tbl]");
      if (!button) return;
      if (button.dataset.kmTbl === "copy") {
        copyTable(tableForm, button);
        return;
      }
      if (button.dataset.kmTbl === "dock") {
        toolsBeside = !toolsBeside;
        try {
          localStorage.setItem(TOOLS_BESIDE_KEY, toolsBeside ? "1" : "0");
        } catch {
          // storage unavailable (private window): the choice lasts this page only
        }
        placeTableTools(tableForm.closest(".km-block"));
        return;
      }
      if (button.dataset.kmTbl === "title") {
        const title = tableForm.querySelector("[data-km-table-title]");
        title.hidden = false;
        title.focus();
        return;
      }
      const table = tableOf(tableForm);
      const rows = [...table.rows];
      const cell = lastCell && table.contains(lastCell) ? lastCell : rows[rows.length - 1].cells[0];
      const row = cell.parentElement;
      const col = cell.cellIndex;
      const action = button.dataset.kmTbl;
      if (action === "row") addRow(table, row).cells[0].focus();
      else if (action === "col") {
        rows.forEach((tr) => tr.cells[Math.min(col, tr.cells.length - 1)].after(newCell()));
        const cols = colsOf(table);
        cols[Math.min(col, cols.length - 1)]?.after(newCol());
        fitWidth(table);
      }
      else if (action === "del-row" && rows.length > 1) {
        // Keep working where you were: the row that takes its place, same column.
        const next = row.nextElementSibling || row.previousElementSibling;
        row.remove();
        lastCell = next.cells[Math.min(col, next.cells.length - 1)];
        lastCell.focus();
      } else if (action === "del-col" && rows[0].cells.length > 1) {
        rows.forEach((tr) => tr.cells[col]?.remove());
        colsOf(table)[col]?.remove();
        fitWidth(table);
        lastCell = row.cells[Math.min(col, row.cells.length - 1)];
        lastCell.focus();
      } else {
        return; // the last row / column stays — nothing changed, nothing to save
      }
      tableChanged(tableForm);
    });
    // Tab / Shift+Tab walk the cells; Tab in the last cell adds a row. Enter is
    // a line break inside the cell (a <div> paragraph, which Firefox makes,
    // would be unwrapped by the cell sanitiser and the lines run together).
    tableForm.addEventListener("keydown", (event) => {
      const cell = event.target.closest?.("td");
      if (!cell || event.isComposing) return;
      if (event.key === "Enter") {
        event.preventDefault();
        document.execCommand("insertLineBreak");
        return;
      }
      if (event.key !== "Tab") return;
      event.preventDefault();
      const table = tableOf(tableForm);
      const cells = [...table.querySelectorAll("td")];
      const next = cells.indexOf(cell) + (event.shiftKey ? -1 : 1);
      if (next >= cells.length) {
        addRow(table).cells[0].focus();
        tableChanged(tableForm);
      } else if (next >= 0) {
        cells[next].focus();
      }
    });
    // Pasting tab-separated text (from Excel / OneNote) or "A | B" lines (a
    // table copied from a board) fills cells from the focused one, adding
    // rows and columns as needed.
    tableForm.addEventListener("paste", (event) => {
      // The caret may sit inside formatting (<b>, <a>) within the cell.
      const cell = event.target.closest?.("td");
      if (!cell) return;
      const text = event.clipboardData?.getData("text/plain") || "";
      const grid = text.includes("\t") ? L.tsvToGrid(text) : L.pipeToGrid(text);
      if (!grid) return;
      event.preventDefault();
      const table = tableOf(tableForm);
      const r0 = cell.parentElement.rowIndex;
      const c0 = cell.cellIndex;
      grid.forEach((line, dr) => {
        while (table.rows.length <= r0 + dr) addRow(table);
        line.forEach((value, dc) => {
          while (table.rows[r0 + dr].cells.length <= c0 + dc) addColumnAtEnd(table);
          table.rows[r0 + dr].cells[c0 + dc].textContent = value;
        });
      });
      fitWidth(table);
      tableChanged(tableForm);
    });
    // An untitled table keeps no room for a title: the Title button shows the
    // field, and leaving it empty hides it again.
    tableForm.addEventListener("focusout", (event) => {
      const title = event.target.closest?.("[data-km-table-title]");
      if (title && !title.value.trim()) title.hidden = true;
    });
    wireTableResize(tableForm);
  }

  // ── table tools: a floating bar on top of or beside the table ────────
  // The bar is the table's own .km-table-tools (so its buttons keep working
  // through the form's handlers), fixed-positioned so it takes no room. On
  // top it sits just above the table, or above the whole board when that
  // would cover the board's top bar; beside, it sits to the table's right
  // (left when there's no room). The ⇄ button switches, for every table, and
  // the browser remembers it.
  const TOOLS_BESIDE_KEY = "km-table-tools-beside";
  const TOOLS_GAP = 4;
  let toolsBeside = false;
  try {
    toolsBeside = localStorage.getItem(TOOLS_BESIDE_KEY) === "1";
  } catch {
    // storage unavailable: tools start on top
  }
  let toolsFor = null;
  function placeTableTools(block) {
    const tools = block?.querySelector(".km-table-tools");
    if (!tools) return;
    toolsFor = block;
    tools.classList.toggle("is-side", toolsBeside);
    const dock = tools.querySelector('[data-km-tbl="dock"]');
    const label = toolsBeside ? "Move these tools above the table" : "Move these tools beside the table";
    dock.title = label;
    dock.setAttribute("aria-label", label);
    // Beside the table itself (narrower than the board once its columns have
    // widths, wider when it scrolls), kept to the board's visible width.
    const table = block.querySelector("table").getBoundingClientRect();
    const body = block.closest("[data-km-blocks]")?.getBoundingClientRect() || table;
    const rect = {
      top: tools.closest("form").getBoundingClientRect().top, // the title, when shown
      left: Math.max(table.left, body.left),
      right: Math.min(table.right, body.right),
    };
    const width = tools.offsetWidth;
    const height = tools.offsetHeight;
    let left;
    let top;
    if (toolsBeside) {
      left = rect.right + TOOLS_GAP;
      if (left + width > window.innerWidth - 4) left = rect.left - width - TOOLS_GAP;
      top = rect.top;
    } else {
      left = rect.left;
      top = rect.top - height - TOOLS_GAP;
      const bar = block.closest(".km-board")?.querySelector("[data-km-board-bar]")?.getBoundingClientRect();
      if (bar && top < bar.bottom) top = bar.top - height - TOOLS_GAP;
    }
    tools.style.left = `${Math.max(4, Math.min(left, window.innerWidth - width - 4))}px`;
    tools.style.top = `${Math.max(4, Math.min(top, window.innerHeight - height - 4))}px`;
  }
  const tableBlockOf = (event) => event.target.closest?.(".km-block--table") || null;
  canvas.addEventListener("pointerover", (event) => {
    const block = tableBlockOf(event);
    if (block) placeTableTools(block); // again on each entry: the table may have changed size
  });
  canvas.addEventListener("focusin", (event) => {
    const block = tableBlockOf(event);
    if (block) placeTableTools(block);
  });
  const replaceTools = () => {
    if (toolsFor?.isConnected) placeTableTools(toolsFor);
  };
  document.addEventListener("scroll", replaceTools, true);
  window.addEventListener("resize", replaceTools);

  // ── table column / row resize: drag a cell border ─────────────────────
  // Drag a column's right edge or a row's bottom edge (a cell's left / top
  // edge counts for the column / row before it). The first column drag fixes
  // every column at its current width so the others stay put. A row height is
  // a minimum: the row still grows with its text. Double-click a border to go
  // back to automatic: all column widths, or that one row's height.
  const EDGE = 5;
  const MIN_COL = 40;
  const MIN_ROW = 20;
  const DOUBLE_MS = 400;
  function edgeAt(table, event) {
    const cell = event.target.closest?.("td");
    if (!cell || !table.contains(cell)) return null;
    const box = cell.getBoundingClientRect();
    const tr = cell.parentElement;
    if (event.clientX >= box.right - EDGE) return { kind: "col", index: cell.cellIndex };
    if (event.clientX <= box.left + EDGE && cell.cellIndex > 0) return { kind: "col", index: cell.cellIndex - 1 };
    if (event.clientY >= box.bottom - EDGE) return { kind: "row", index: tr.rowIndex };
    if (event.clientY <= box.top + EDGE && tr.rowIndex > 0) return { kind: "row", index: tr.rowIndex - 1 };
    return null;
  }
  function freezeWidths(table) {
    if (colsOf(table).length) return;
    const group = document.createElement("colgroup");
    [...table.rows[0].cells].forEach((td) => group.appendChild(newCol(Math.max(MIN_COL, Math.round(td.getBoundingClientRect().width)))));
    table.prepend(group);
    table.classList.add("has-col-widths");
    fitWidth(table);
  }
  function resetSize(table, edge) {
    if (edge.kind === "col") {
      table.querySelector(":scope > colgroup")?.remove();
      table.classList.remove("has-col-widths");
      fitWidth(table);
    } else {
      table.rows[edge.index].style.height = "";
    }
  }
  function wireTableResize(tableForm) {
    let drag = null;
    let lastDown = null;
    const markEdge = (table, edge) => {
      table.classList.toggle("is-col-edge", edge?.kind === "col");
      table.classList.toggle("is-row-edge", edge?.kind === "row");
    };
    tableForm.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      const table = tableOf(tableForm);
      const edge = edgeAt(table, event);
      if (!edge) return;
      event.preventDefault(); // no caret, no text selection
      const now = Date.now();
      if (lastDown && lastDown.kind === edge.kind && lastDown.index === edge.index && now - lastDown.at < DOUBLE_MS) {
        lastDown = null;
        resetSize(table, edge);
        tableChanged(tableForm);
        return;
      }
      lastDown = { ...edge, at: now };
      drag = { ...edge, x: event.clientX, y: event.clientY, started: false };
      table.setPointerCapture(event.pointerId);
    });
    tableForm.addEventListener("pointermove", (event) => {
      const table = tableOf(tableForm);
      if (!drag) {
        markEdge(table, event.buttons ? null : edgeAt(table, event));
        return;
      }
      const dx = event.clientX - drag.x;
      const dy = event.clientY - drag.y;
      if (!drag.started) {
        if (Math.abs(drag.kind === "col" ? dx : dy) < 3) return; // a click, not a drag
        drag.started = true;
        lastDown = null; // a drag is never the first half of a double-click
        if (drag.kind === "col") {
          freezeWidths(table);
          drag.target = colsOf(table)[drag.index];
          drag.start = parseInt(drag.target.style.width, 10);
        } else {
          drag.target = table.rows[drag.index];
          drag.start = drag.target.getBoundingClientRect().height;
        }
      }
      if (drag.kind === "col") {
        drag.target.style.width = `${Math.max(MIN_COL, Math.round(drag.start + dx))}px`;
        fitWidth(table);
      } else {
        drag.target.style.height = `${Math.max(MIN_ROW, Math.round(drag.start + dy))}px`;
      }
    });
    const endDrag = (event) => {
      if (!drag) return;
      const table = tableOf(tableForm);
      if (table.hasPointerCapture?.(event.pointerId)) table.releasePointerCapture(event.pointerId);
      const moved = drag.started;
      drag = null;
      markEdge(table, null);
      if (moved) tableChanged(tableForm);
    };
    tableForm.addEventListener("pointerup", endDrag);
    tableForm.addEventListener("pointercancel", endDrag);
    tableForm.addEventListener("pointerleave", () => {
      if (!drag) markEdge(tableOf(tableForm), null);
    });
  }

  // ── Copy: the table as "A | B" text (and as HTML for Excel / Word) ─────
  const escapeHtml = (value) => {
    const holder = document.createElement("div");
    holder.textContent = value;
    return holder.innerHTML;
  };
  async function copyTable(tableForm, button) {
    const rows = [...tableOf(tableForm).rows].map((tr) => [...tr.cells].map((td) => td.innerText.replace(/\n+$/, "")));
    const text = L.gridToPipe(rows);
    const html = `<table>${rows.map((row) => `<tr>${row.map((value) => `<td>${escapeHtml(value).replace(/\n/g, "<br>")}</td>`).join("")}</tr>`).join("")}</table>`;
    // A copy event carries both formats and works without a secure context.
    let copied = false;
    const onCopy = (event) => {
      event.clipboardData.setData("text/plain", text);
      event.clipboardData.setData("text/html", html);
      event.preventDefault();
      copied = true;
    };
    document.addEventListener("copy", onCopy);
    try {
      document.execCommand("copy");
    } finally {
      document.removeEventListener("copy", onCopy);
    }
    if (!copied) {
      try {
        await navigator.clipboard.writeText(text);
        copied = true;
      } catch {
        toast("Couldn't copy the table.", "danger");
        return;
      }
    }
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = "Copy"; }, 1200);
  }

  const wirers = [["[data-km-text]", wireText], ["[data-km-code]", wireCode], ["[data-km-table-form]", wireTable]];
  function wireBlocks(scope) {
    wirers.forEach(([selector, wire]) => scope.querySelectorAll(selector).forEach(wire));
  }

  function insertBlock(board, html, after = null) {
    const holder = document.createElement("div");
    holder.innerHTML = html.trim();
    const block = holder.firstElementChild;
    if (after) after.after(block);
    else board.querySelector("[data-km-blocks]").appendChild(block);
    block.querySelectorAll("form[data-autosave]").forEach(wireAutosaveForm);
    wireBlocks(block);
    return block;
  }

  canvas.addEventListener("km:board-added", (event) => {
    event.detail.querySelectorAll("form[data-autosave]").forEach(wireAutosaveForm);
    wireBlocks(event.detail);
  });

  // ── + Add menu (one shared menu, opened from any board's top bar) ─────
  const menu = document.querySelector("[data-km-add-menu-pop]");
  let menuBoard = null;
  canvas.addEventListener("click", (event) => {
    const opener = event.target.closest("[data-km-add-menu]");
    if (!opener) return;
    event.stopPropagation();
    menuBoard = opener.closest(".km-board");
    const rect = opener.getBoundingClientRect();
    menu.hidden = false;
    menu.style.left = `${rect.left + window.scrollX}px`;
    menu.style.top = `${rect.bottom + window.scrollY + 4}px`;
  });
  document.addEventListener("click", (event) => {
    if (!event.target.closest("[data-km-add-menu], [data-km-add-menu-pop]")) menu.hidden = true;
  });
  menu.addEventListener("click", async (event) => {
    const item = event.target.closest("[data-km-add]");
    if (!item || !menuBoard) return;
    menu.hidden = true;
    const board = menuBoard;
    const kind = item.dataset.kmAdd;
    if (kind === "image" || kind === "file") {
      pickFile(board, kind);
      return;
    }
    const response = await post(`/knowledge/boards/${board.dataset.boardId}/blocks`, form({ kind }));
    if (!response || !response.ok) return;
    const block = insertBlock(board, await response.text());
    block.querySelector("[data-km-text], textarea, td")?.focus();
  });

  // ── format toolbar for text blocks ────────────────────────────────────
  const toolbar = document.querySelector("[data-km-format]");
  let toolbarFor = null;
  // Sits just above the text block being edited (kept on screen), and follows
  // it when the window, the canvas or a board body scrolls.
  function placeToolbar() {
    if (!toolbarFor) return;
    const rect = toolbarFor.getBoundingClientRect();
    // Just above the text being edited — or above the whole board when that
    // would cover the board's own top bar (its title, + Add, maximize, delete).
    const bar = toolbarFor.closest(".km-board")?.querySelector("[data-km-board-bar]")?.getBoundingClientRect();
    let top = rect.top - toolbar.offsetHeight - 6;
    if (bar && top < bar.bottom) top = bar.top - toolbar.offsetHeight - 6;
    toolbar.style.left = `${rect.left + window.scrollX}px`;
    toolbar.style.top = `${Math.max(4, top) + window.scrollY}px`;
  }
  document.addEventListener("focusin", (event) => {
    const editor = event.target.closest("[data-km-text]");
    if (!editor) return;
    toolbarFor = editor;
    toolbar.hidden = false;
    placeToolbar();
  });
  document.addEventListener("scroll", placeToolbar, true);
  window.addEventListener("resize", placeToolbar);
  document.addEventListener("focusout", (event) => {
    if (!event.target.closest("[data-km-text]")) return;
    setTimeout(() => {
      if (document.activeElement?.closest?.("[data-km-text]")) return;
      toolbar.hidden = true;
      toolbarFor = null;
    }, 150);
  });
  toolbar.addEventListener("mousedown", (event) => event.preventDefault()); // keep the text selection
  toolbar.addEventListener("click", (event) => {
    const button = event.target.closest("[data-cmd]");
    if (!button) return;
    let argument = button.dataset.arg || null;
    if (button.dataset.cmd === "createLink") {
      argument = (window.prompt("Link URL (https://…)", "https://") || "").trim();
      if (!argument || argument === "https://") return;
      // Without a scheme "example.com" would be a link relative to this page;
      // only http(s) and mailto survive the server's sanitiser anyway.
      if (!/^(https?:|mailto:)/i.test(argument)) argument = `https://${argument.replace(/^\/+/, "")}`;
    }
    document.execCommand(button.dataset.cmd, false, argument);
  });

  // ── move a block up / down within its board ───────────────────────────
  canvas.addEventListener("click", (event) => {
    const up = event.target.closest("[data-km-block-up]");
    const down = event.target.closest("[data-km-block-down]");
    if (!up && !down) return;
    const block = (up || down).closest(".km-block");
    const list = block.parentElement;
    if (up && block.previousElementSibling) list.insertBefore(block, block.previousElementSibling);
    else if (down && block.nextElementSibling) list.insertBefore(block.nextElementSibling, block);
    else return;
    const order = [...list.children].map((el) => el.dataset.blockId).join(",");
    post(`/knowledge/boards/${block.closest(".km-board").dataset.boardId}/blocks/reorder`, form({ order }));
  });

  // Enter in a snippet title or an image caption would submit its form natively (a full page
  // reload); leave the field instead, which flushes the autosave.
  canvas.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && event.target.matches(".km-code input[name='title'], .km-caption, [data-km-table-title]")) {
      event.preventDefault();
      event.target.blur();
    }
  });

  // ── images and files: + Add picker, Ctrl+V paste, drag and drop ───────
  const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;
  const picker = document.createElement("input");
  picker.type = "file";
  picker.multiple = true;
  picker.hidden = true;
  document.body.appendChild(picker);
  let pickerBoard = null;

  async function upload(board, file) {
    if (file.size > MAX_UPLOAD_BYTES) {
      toast(`${file.name} is larger than 50 MB.`, "danger");
      return;
    }
    const body = new FormData();
    body.append("file", file, file.name || "pasted-image.png");
    const response = await post(`/knowledge/boards/${board.dataset.boardId}/upload`, body);
    if (!response) return;
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      toast(data.error || "Upload failed.", "danger");
      return;
    }
    const block = insertBlock(board, await response.text());
    // A PNG is swapped for its compressed copy a moment after upload; a
    // fetch caught mid-swap fails, so a new image gets one more try.
    const img = block.querySelector(".km-image img");
    img?.addEventListener("error", () => setTimeout(() => {
      img.src = `${img.src.split("?")[0]}?retry=${Date.now()}`;
    }, 400), { once: true });
  }

  function pickFile(board, kind) {
    pickerBoard = board;
    picker.accept = kind === "image" ? "image/*" : "";
    picker.value = "";
    picker.click();
  }
  picker.addEventListener("change", () => {
    const board = pickerBoard;
    [...picker.files].forEach((file) => upload(board, file));
  });

  // Ctrl+V with an image on the clipboard adds it to the board you're in (or
  // the selected one); text pastes are left to the field being edited.
  document.addEventListener("paste", (event) => {
    const images = [...(event.clipboardData?.files || [])].filter((file) => file.type.startsWith("image/"));
    // A copy that carries text too (Excel, Word) is a text paste for the field.
    if (!images.length || event.clipboardData.getData("text/plain").trim()) return;
    const board = event.target.closest?.(".km-board") || canvas.querySelector(".km-board.is-selected");
    if (!board) return;
    event.preventDefault();
    images.forEach((file) => upload(board, file));
  });

  // Text that reads as a table ("A | B" lines or a Markdown table) pasted
  // into a text block becomes a table block right after it, replacing the
  // text block if that was empty; pasted with a board selected and no field
  // focused, it goes at the end of that board. A cell fills itself (see
  // wireTable); code, titles and captions keep plain text.
  async function addTableFromGrid(board, grid, afterBlock) {
    const content = JSON.stringify({ head_row: true, head_col: false, rows: grid.map((row) => row.map(escapeHtml)) });
    const fields = { kind: "table", content };
    if (afterBlock) fields.after_block_id = afterBlock.dataset.blockId;
    const response = await post(`/knowledge/boards/${board.dataset.boardId}/blocks`, form(fields));
    if (!response || !response.ok) return;
    insertBlock(board, await response.text(), afterBlock);
    const text = afterBlock?.querySelector("[data-km-text]");
    if (text && !text.textContent.trim() && !text.querySelector("img")) {
      const removed = await post(`/knowledge/blocks/${afterBlock.dataset.blockId}/delete`, form({}));
      if (removed && removed.ok) afterBlock.remove();
    }
    toast(`Pasted as a table (${grid.length} row${grid.length === 1 ? "" : "s"}).`);
  }
  document.addEventListener("paste", (event) => {
    const target = event.target instanceof Element ? event.target : null;
    if (target?.closest("td, input, textarea, select")) return;
    const grid = L.pipeToGrid(event.clipboardData?.getData("text/plain") || "");
    if (!grid) return;
    const textBlock = target?.closest(".km-text")?.closest(".km-block") || null;
    let board = null;
    if (textBlock) board = textBlock.closest(".km-board");
    else if (!target?.closest("[contenteditable]")) board = canvas.querySelector(".km-board.is-selected");
    if (!board) return;
    event.preventDefault();
    addTableFromGrid(board, grid, textBlock);
  });

  // File drags are accepted anywhere on the canvas, so a drop that misses a
  // board never makes the browser open the file and leave the page.
  canvas.addEventListener("dragover", (event) => {
    if (!event.dataTransfer?.types.includes("Files")) return;
    event.preventDefault();
    const board = event.target.closest(".km-board");
    canvas.querySelectorAll(".km-board.is-drop-target").forEach((b) => b !== board && b.classList.remove("is-drop-target"));
    board?.classList.add("is-drop-target");
  });
  canvas.addEventListener("dragleave", (event) => {
    const board = event.target.closest(".km-board");
    if (board && !board.contains(event.relatedTarget)) board.classList.remove("is-drop-target");
  });
  canvas.addEventListener("drop", (event) => {
    if (!event.dataTransfer?.files.length) return;
    event.preventDefault();
    canvas.querySelectorAll(".km-board.is-drop-target").forEach((b) => b.classList.remove("is-drop-target"));
    const board = event.target.closest(".km-board");
    if (!board) return;
    [...event.dataTransfer.files].forEach((file) => upload(board, file));
  });

  wireBlocks(canvas);
})();
