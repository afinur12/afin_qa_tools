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
  const tableOf = (tableForm) => tableForm.querySelector("table");
  function serializeTable(tableForm) {
    const table = tableOf(tableForm);
    tableForm.querySelector("[data-km-table-value]").value = JSON.stringify({
      head_row: table.classList.contains("has-head-row"),
      head_col: table.classList.contains("has-head-col"),
      rows: [...table.rows].map((tr) => [...tr.cells].map((td) => td.innerHTML)),
    });
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
    tableForm.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-km-tbl]");
      if (!button) return;
      const table = tableOf(tableForm);
      const rows = [...table.rows];
      const cell = lastCell && table.contains(lastCell) ? lastCell : rows[rows.length - 1].cells[0];
      const row = cell.parentElement;
      const col = cell.cellIndex;
      const action = button.dataset.kmTbl;
      if (action === "row") addRow(table, row).cells[0].focus();
      else if (action === "col") rows.forEach((tr) => tr.cells[Math.min(col, tr.cells.length - 1)].after(newCell()));
      else if (action === "del-row" && rows.length > 1) {
        // Keep working where you were: the row that takes its place, same column.
        const next = row.nextElementSibling || row.previousElementSibling;
        row.remove();
        lastCell = next.cells[Math.min(col, next.cells.length - 1)];
        lastCell.focus();
      } else if (action === "del-col" && rows[0].cells.length > 1) {
        rows.forEach((tr) => tr.cells[col]?.remove());
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
    // Pasting tab-separated text (from Excel / OneNote) fills cells from the
    // focused one, adding rows and columns as needed.
    tableForm.addEventListener("paste", (event) => {
      // The caret may sit inside formatting (<b>, <a>) within the cell.
      const cell = event.target.closest?.("td");
      if (!cell) return;
      const text = event.clipboardData?.getData("text/plain") || "";
      if (!text.includes("\t")) return;
      event.preventDefault();
      const table = tableOf(tableForm);
      const grid = window.KnowledgeLayout.tsvToGrid(text);
      const r0 = cell.parentElement.rowIndex;
      const c0 = cell.cellIndex;
      grid.forEach((line, dr) => {
        while (table.rows.length <= r0 + dr) addRow(table);
        line.forEach((value, dc) => {
          while (table.rows[r0 + dr].cells.length <= c0 + dc) [...table.rows].forEach((tr) => tr.appendChild(newCell()));
          table.rows[r0 + dr].cells[c0 + dc].textContent = value;
        });
      });
      tableChanged(tableForm);
    });
  }

  const wirers = [["[data-km-text]", wireText], ["[data-km-code]", wireCode], ["[data-km-table-form]", wireTable]];
  function wireBlocks(scope) {
    wirers.forEach(([selector, wire]) => scope.querySelectorAll(selector).forEach(wire));
  }

  function insertBlock(board, html) {
    const holder = document.createElement("div");
    holder.innerHTML = html.trim();
    const block = holder.firstElementChild;
    board.querySelector("[data-km-blocks]").appendChild(block);
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
    toolbar.style.left = `${rect.left + window.scrollX}px`;
    toolbar.style.top = `${Math.max(4, rect.top - toolbar.offsetHeight - 6) + window.scrollY}px`;
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
    if (event.key === "Enter" && event.target.matches(".km-code input[name='title'], .km-caption")) {
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
