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

  const wirers = [["[data-km-text]", wireText], ["[data-km-code]", wireCode]];
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
    // km:add-upload-kinds
    const response = await post(`/knowledge/boards/${board.dataset.boardId}/blocks`, form({ kind }));
    if (!response || !response.ok) return;
    const block = insertBlock(board, await response.text());
    block.querySelector("[data-km-text], textarea, td")?.focus();
  });

  // ── format toolbar for text blocks ────────────────────────────────────
  const toolbar = document.querySelector("[data-km-format]");
  document.addEventListener("focusin", (event) => {
    const editor = event.target.closest("[data-km-text]");
    if (!editor) return;
    const rect = (editor.closest(".km-board") || editor).getBoundingClientRect();
    toolbar.hidden = false;
    toolbar.style.left = `${rect.left + window.scrollX}px`;
    toolbar.style.top = `${Math.max(0, rect.top + window.scrollY - toolbar.offsetHeight - 6)}px`;
  });
  document.addEventListener("focusout", (event) => {
    if (!event.target.closest("[data-km-text]")) return;
    setTimeout(() => {
      if (!document.activeElement?.closest?.("[data-km-text]")) toolbar.hidden = true;
    }, 150);
  });
  toolbar.addEventListener("mousedown", (event) => event.preventDefault()); // keep the text selection
  toolbar.addEventListener("click", (event) => {
    const button = event.target.closest("[data-cmd]");
    if (!button) return;
    let argument = button.dataset.arg || null;
    if (button.dataset.cmd === "createLink") {
      argument = window.prompt("Link URL (https://…)", "https://");
      if (!argument) return;
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

  wireBlocks(canvas);
})();
