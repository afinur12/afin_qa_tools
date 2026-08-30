(function () {
  // Used by both the {{var}}-in-a-plain-field overlay and the code-editor
  // overlay (further down). Declared here, right at the top: it's a `const`,
  // not a `function` — unlike function declarations, `const` isn't
  // initialized until its line actually runs, so anything below that tried
  // to use it before reaching that line would hit "Cannot access
  // 'VAR_TOKEN_PATTERN' before initialization" (a real bug this file had,
  // caught by attachCodeEditor being called unconditionally — i.e. before
  // the builder-only early-return below — for the Built-in Variables page).
  const VAR_TOKEN_PATTERN = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_-]*)\s*\}\}/g;

  // Same TDZ hazard as above: wrapVarTokens (below) runs during the very
  // first render of the URL bar, well before the {{variable}} autocomplete
  // section further down this file would otherwise define this — so it has
  // to live up here too. Pages that don't render the Builder (Built-in
  // Variables' own script editor, etc.) never set window.__AC_VARIABLES__,
  // hence the fallback; nothing on those pages contains {{name}} tokens.
  const AC_VARIABLES = window.__AC_VARIABLES__ || [];
  const AC_VARIABLE_NAMES = new Set(AC_VARIABLES.map((v) => v.name));

  // Matches icon_chevron() in macros.html — used for the collapsible
  // Response Headers <details> summary, built as a plain string here since
  // it's assembled into an innerHTML template, not rendered by Jinja.
  const CHEVRON_SVG = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>';

  // Same TDZ hazard as VAR_TOKEN_PATTERN above: currentHeaders() (defined
  // much further down) reads this, and now gets called during the request
  // body editor's own initial, synchronous setup (attachCodeEditor's
  // language resolver calls detectBodyLanguage(currentHeaders(), ...)) —
  // which runs before execution ever reaches this `const`'s original
  // declaration line whenever a request already has a saved header at
  // page load. That threw "Cannot access 'SENSITIVE_HEADER_PATTERN'
  // before initialization", an uncaught exception that aborted the rest
  // of this script — including the Send button's own click listener
  // further down, never wiring it up.
  const SENSITIVE_HEADER_PATTERN = /authorization|cookie|api[-_]?key|token|secret|password/i;

  // Same TDZ hazard again: attachCodeEditor (used for both the request
  // body and every variable's Script field) is itself called unconditionally
  // a few lines down, for the Built-in/standalone Variables page — which
  // has no request body, so this is the only attachCodeEditor call that
  // page ever makes, well before a `let` declared near attachCodeEditor's
  // own definition further down would have run.
  let codeWidthMirror = null;
  function measureNaturalTextWidth(referenceField, text) {
    if (!codeWidthMirror) {
      codeWidthMirror = document.createElement("div");
      codeWidthMirror.style.cssText = "position:absolute; visibility:hidden; left:-99999px; top:0; white-space:pre;";
      document.body.appendChild(codeWidthMirror);
    }
    const cs = getComputedStyle(referenceField);
    codeWidthMirror.style.fontFamily = cs.fontFamily;
    codeWidthMirror.style.fontSize = cs.fontSize;
    codeWidthMirror.style.fontWeight = cs.fontWeight;
    codeWidthMirror.style.letterSpacing = cs.letterSpacing;
    codeWidthMirror.textContent = text;
    return codeWidthMirror.scrollWidth;
  }

  // Registered unconditionally: the Variables modal's Value/Script toggle
  // is also used on the standalone Built-in Variables page, which has none
  // of the builder-only elements the early-return below guards.
  document.addEventListener("change", (event) => {
    if (!event.target.matches("[data-ac-var-kind-select]")) return;
    const form = event.target.closest("form");
    const valueField = form.querySelector("[data-ac-var-value-field]");
    const scriptField = form.querySelector("[data-ac-var-script-field]");
    const isScript = event.target.value === "SCRIPT";
    if (valueField) valueField.hidden = isScript;
    if (scriptField) scriptField.hidden = !isScript;
    // The script textarea's auto-grown height was meaningless while this
    // field itself was hidden (display:none) — now that it's visible,
    // force its already-wired code-editor listener to recompute it.
    if (isScript) scriptField?.querySelector("[data-ac-script-editor]")?.dispatchEvent(new Event("input"));
  });

  // Also unconditional: every variable's Script field (builder page and
  // Built-in Variables page alike) gets the same editable-code-block
  // treatment as the request body. attachCodeEditor/renderCodeHighlight
  // are `function` declarations further down this same IIFE — hoisted,
  // so calling them here (ahead of their literal source position, and
  // ahead of the builder-only early-return below) is safe.
  document.querySelectorAll("[data-ac-script-editor]").forEach((ta) => attachCodeEditor(ta, "python"));

  // A script field wired up while its modal was still hidden has a stale
  // auto-grown height — force a resync the moment its modal opens.
  document.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-modal-open]");
    if (!trigger) return;
    const modal = document.getElementById(trigger.dataset.modalOpen);
    modal?.querySelectorAll("[data-ac-script-editor]").forEach((ta) => ta.dispatchEvent(new Event("input")));
  });

  const root = document.querySelector("[data-ac-tree]");
  if (!root) return; // not on the API Client builder page

  const CURRENT = window.__AC_CURRENT__ || { id: null, method: "GET", url: "", headers: [], body: "", collection_id: null };
  // Set while a tab switch is replaying its stored fields into the DOM, so
  // the synthetic "input" events that replay fires (needed so highlight
  // overlays / param sync stay correct) aren't mistaken for a real user
  // edit by the autosave/tab-sync listeners below.
  let applyingTab = false;

  // ── Toast (no full-page redirect here, so the flash-cookie mechanism the
  // rest of the app relies on doesn't apply — a minimal local version). ──
  function toast(message, kind) {
    const el = document.createElement("div");
    el.className = `toast toast--${kind || "success"}`;
    el.setAttribute("role", "status");
    el.textContent = message;
    document.body.appendChild(el);
    requestAnimationFrame(() => el.classList.add("is-visible"));
    setTimeout(() => {
      el.classList.remove("is-visible");
      setTimeout(() => el.remove(), 250);
    }, 3200);
  }

  async function copyText(text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      const scratch = document.createElement("textarea");
      scratch.value = text;
      scratch.setAttribute("readonly", "");
      scratch.style.position = "fixed";
      scratch.style.opacity = "0";
      document.body.appendChild(scratch);
      scratch.select();
      document.execCommand("copy");
      document.body.removeChild(scratch);
    }
  }

  // ── Tree: expand/collapse + search filter ────────────────────────────────
  root.querySelectorAll("[data-ac-tree-toggle]").forEach((row) => {
    row.querySelector(".ac-chev").addEventListener("click", (event) => {
      event.preventDefault();
      row.classList.toggle("is-collapsed");
      const children = row.nextElementSibling;
      if (children && children.classList.contains("ac-tree-children")) {
        children.classList.toggle("is-collapsed");
      }
    });
  });

  const treeSearch = document.querySelector("[data-ac-tree-search]");
  if (treeSearch) {
    treeSearch.addEventListener("input", () => {
      const q = treeSearch.value.trim().toLowerCase();
      root.querySelectorAll(".ac-tree-row").forEach((row) => {
        const name = row.querySelector(".ac-tree-name").textContent.toLowerCase();
        // Requests also carry their URL (data-ac-tree-url) — a saved curl
        // command's identity lives in its URL as much as its name, so a
        // search for a path segment or host should surface it too.
        const url = (row.dataset.acTreeUrl || "").toLowerCase();
        const matches = !q || name.includes(q) || url.includes(q);
        row.closest("a, div").style.display = matches ? "" : "none";
      });
    });
  }

  // ── Collections drawer: resizable width ──────────────────────────────────
  const DRAWER_WIDTH_KEY = "qa-toolbox:api-client-drawer-width";
  const drawerPanel = document.querySelector(".modal--drawer");
  const drawerHandle = document.querySelector("[data-ac-drawer-resize]");
  if (drawerPanel && drawerHandle) {
    try {
      const savedWidth = localStorage.getItem(DRAWER_WIDTH_KEY);
      if (savedWidth) drawerPanel.style.width = `${savedWidth}px`;
    } catch {
      /* storage unavailable — falls back to the CSS default width */
    }

    let dragStartX = 0;
    let dragStartWidth = 0;

    function onDragMove(event) {
      const clientX = event.touches ? event.touches[0].clientX : event.clientX;
      // Anchored to the right edge, so dragging left (negative delta) grows it.
      const next = dragStartWidth + (dragStartX - clientX);
      const min = 280;
      const max = Math.round(window.innerWidth * 0.88);
      drawerPanel.style.width = `${Math.min(max, Math.max(min, next))}px`;
    }

    function onDragEnd() {
      document.removeEventListener("mousemove", onDragMove);
      document.removeEventListener("mouseup", onDragEnd);
      document.removeEventListener("touchmove", onDragMove);
      document.removeEventListener("touchend", onDragEnd);
      document.body.classList.remove("is-resizing-drawer");
      try {
        localStorage.setItem(DRAWER_WIDTH_KEY, String(Math.round(drawerPanel.getBoundingClientRect().width)));
      } catch {
        /* storage unavailable — width just won't persist across reloads */
      }
    }

    function onDragStart(event) {
      event.preventDefault();
      dragStartX = event.touches ? event.touches[0].clientX : event.clientX;
      dragStartWidth = drawerPanel.getBoundingClientRect().width;
      document.body.classList.add("is-resizing-drawer");
      document.addEventListener("mousemove", onDragMove);
      document.addEventListener("mouseup", onDragEnd);
      document.addEventListener("touchmove", onDragMove, { passive: false });
      document.addEventListener("touchend", onDragEnd);
    }

    drawerHandle.addEventListener("mousedown", onDragStart);
    drawerHandle.addEventListener("touchstart", onDragStart, { passive: false });
  }

  // ── Layout toggle (stacked / split) ──────────────────────────────────────
  const LAYOUT_KEY = "qa-toolbox:api-client-layout";
  const WRAP_KEY = "qa-toolbox:api-client-wrap";
  const layoutWrap = document.querySelector("[data-ac-layout]");
  const layoutButtons = document.querySelectorAll("[data-ac-layout-btn]");

  function applyLayout(mode) {
    if (!layoutWrap) return;
    layoutWrap.classList.toggle("ac-split", mode === "split");
    layoutWrap.classList.toggle("ac-stacked", mode !== "split");
    layoutButtons.forEach((btn) => btn.classList.toggle("is-active", btn.dataset.acLayoutBtn === mode));
  }

  layoutButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const mode = btn.dataset.acLayoutBtn;
      applyLayout(mode);
      try { localStorage.setItem(LAYOUT_KEY, mode); } catch { /* storage unavailable */ }
    });
  });

  try {
    const saved = localStorage.getItem(LAYOUT_KEY);
    if (saved) applyLayout(saved);
  } catch { /* storage unavailable — stays stacked */ }


  // ── Header rows: add / remove / sensitive flag ───────────────────────────
  const headersContainer = document.querySelector("[data-ac-headers]");
  const headerCount = document.querySelector("[data-ac-header-count]");

  function updateHeaderCount() {
    if (!headerCount) return;
    const filled = headerRows().filter((row) => row.querySelector("[data-ac-header-key]").value.trim()).length;
    headerCount.textContent = String(filled);
  }

  function headerRows() {
    return Array.from(headersContainer.querySelectorAll("[data-ac-header-row]"));
  }

  function addHeaderRow(key, value) {
    const row = document.createElement("tr");
    row.setAttribute("data-ac-header-row", "");
    row.innerHTML = `
      <td><input class="ac-kv-key" data-ac-header-key placeholder="Key" value="${escapeAttr(key || "")}"></td>
      <td><input data-ac-header-value placeholder="Value" value="${escapeAttr(value || "")}"></td>
      <td class="ac-kv-actions">
        <button type="button" class="btn act edit ac-sensitive-flag" data-ac-sensitive-toggle title="Mark sensitive — masked in exported images">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>
        </button>
        <button type="button" class="btn act remove" data-ac-remove-header title="Remove header" aria-label="Remove header">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
        </button>
      </td>`;
    headersContainer.appendChild(row);
    updateHeaderCount();
    initVariableHighlighting(row);
    return row;
  }

  function escapeAttr(s) {
    return String(s).replace(/&/g, "&amp;").replace(/"/g, "&quot;");
  }

  // ── {{variable}} highlighting inside editable fields ─────────────────────
  // A plain <input>/<textarea> can't style part of its own text, so this
  // overlays a non-interactive layer showing the same text with {{name}}
  // tokens colored, and makes the real field's glyphs transparent (keeping
  // a visible caret) so only the overlay's colors show through underneath
  // — the standard trick for "syntax highlighting" inside a native field.
  // Alternates two chip colors across the tokens found in one string, so
  // adjacent variables (e.g. {{amdocs-cm}}{{base_url_dev_tc}} with nothing
  // between them) read as two distinct chips instead of one unbroken block
  // of the same green.
  function wrapVarTokens(html) {
    let index = 0;
    return html.replace(VAR_TOKEN_PATTERN, (match, name) => {
      // Only a token that actually resolves (matches a real built-in/
      // global/collection variable) gets the badge treatment — anything
      // else ({{randomkjfdxk}}, a typo, {{}} you haven't defined yet) is
      // left as plain text so the highlight can be trusted as "this will
      // really substitute", not just "this looks like {{...}}".
      if (!AC_VARIABLE_NAMES.has(name)) return match;
      const cls = index % 2 === 0 ? "ac-var-token" : "ac-var-token-alt";
      index += 1;
      return `<span class="${cls}">${match}</span>`;
    });
  }

  function highlightMarkup(text) {
    return wrapVarTokens(escapeHtml(text));
  }

  function attachVariableHighlight(field) {
    if (!field || field.dataset.acHighlighted) return;
    field.dataset.acHighlighted = "1";

    const computed = getComputedStyle(field);
    const isTextarea = field.tagName === "TEXTAREA";

    const wrap = document.createElement("div");
    wrap.className = "ac-highlight-wrap";
    // Take over whatever flex/width sizing the bare field had, so the
    // wrapper claims the same space in its parent flex row (or block) —
    // a fixed-width header key input and a flex-grow URL bar both need to
    // keep behaving the way they did before being wrapped.
    wrap.style.flex = computed.flex;
    wrap.style.minWidth = computed.minWidth;
    if (isTextarea) wrap.style.width = "100%";

    field.parentNode.insertBefore(wrap, field);
    wrap.appendChild(field);

    const overlay = document.createElement("div");
    overlay.className = "ac-highlight-overlay" + (isTextarea ? " is-multiline" : "");
    wrap.appendChild(overlay);

    ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing",
     "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
     "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth"].forEach((prop) => {
      overlay.style[prop] = computed[prop];
    });

    field.classList.add("ac-highlight-field");
    field.style.flex = "1 1 auto";
    field.style.width = "100%";

    function sync() {
      overlay.innerHTML = highlightMarkup(field.value);
      overlay.scrollLeft = field.scrollLeft;
      overlay.scrollTop = field.scrollTop;
    }
    field.addEventListener("input", sync);
    field.addEventListener("scroll", () => {
      overlay.scrollLeft = field.scrollLeft;
      overlay.scrollTop = field.scrollTop;
    });
    sync();
  }

  // [data-ac-body] is deliberately excluded here — it gets its own fuller
  // treatment (hljs JSON coloring + a line-number gutter, not just
  // {{var}} tokens) via attachBodyCodeEditor below.
  const AC_SIMPLE_HIGHLIGHT_SELECTOR = "[data-ac-url], [data-ac-header-key], [data-ac-header-value], [data-ac-param-key], [data-ac-param-value]";

  function initVariableHighlighting(scope) {
    (scope || document).querySelectorAll(AC_SIMPLE_HIGHLIGHT_SELECTOR).forEach(attachVariableHighlight);
    if (scope && scope.matches && scope.matches(AC_SIMPLE_HIGHLIGHT_SELECTOR)) {
      attachVariableHighlight(scope);
    }
  }

  initVariableHighlighting(document);

  // ── Body language detection — shared by the request body editor and the
  // response payload viewer, so both highlight the same six content types
  // the same way. Content-Type is the primary signal (it's what actually
  // determines the wire format); with none set, fall back to sniffing the
  // body's own shape. xml doubles for html (hljs's xml grammar already
  // handles both); x-www-form-urlencoded and text/plain both render as
  // plaintext — there's no dedicated grammar for key=value&key=value, and
  // it doesn't gain much from token coloring anyway.
  function detectBodyLanguage(headers, body) {
    const found = (headers || []).find(([k]) => (k || "").toLowerCase() === "content-type");
    const ct = (found ? found[1] : "").toLowerCase();
    if (ct.includes("json")) return "json";
    if (ct.includes("graphql")) return "graphql";
    if (ct.includes("xml") || ct.includes("html")) return "xml";
    if (ct) return "plaintext"; // an explicit content-type we don't special-case (urlencoded, text/plain, ...)

    const trimmed = (body || "").trim();
    if (!trimmed) return "json"; // no signal at all yet — matches the field's own default
    if (trimmed[0] === "<") return "xml";
    try {
      JSON.parse(trimmed);
      return "json";
    } catch {
      return "plaintext";
    }
  }

  // ── Editable dark code-block (gutter + hljs syntax + {{var}}) ────────────
  // Shared by the request body and every variable's Script field (Python)
  // — same look, same {{var}} overlay trick, just a different hljs
  // language. `language` may be a plain string (Script fields: always
  // Python) or a function re-evaluated on every sync (the request body:
  // its language can change as Content-Type is edited).
  function renderCodeHighlight(text, language) {
    let html;
    if (window.hljs) {
      try {
        html = window.hljs.highlight(text, { language, ignoreIllegals: true }).value;
      } catch {
        html = escapeHtml(text);
      }
    } else {
      html = escapeHtml(text);
    }
    // Re-wraps {{var}} tokens on top of hljs's own spans. Safe in the
    // common case — a variable used inside a JSON string value, or a
    // Python string literal — since hljs keeps the whole quoted string as
    // one token, so {{name}} stays contiguous in the resulting HTML
    // instead of being split across span boundaries by hljs's tokenizing.
    return wrapVarTokens(html);
  }

  function attachCodeEditor(textarea, language) {
    if (!textarea || textarea.dataset.acCodeEditor) return;
    textarea.dataset.acCodeEditor = "1";
    const container = textarea.closest(".ac-code-editor");
    const overlay = container?.querySelector(".ac-code-overlay code");
    const gutter = container?.querySelector(".snippet-gutter");
    const inner = container?.querySelector(".ac-code-editor-inner");
    const scroller = container?.querySelector(".snippet-code");

    function sync() {
      const text = textarea.value;
      const lang = typeof language === "function" ? language() : language;
      if (overlay) overlay.innerHTML = renderCodeHighlight(text, lang);
      if (gutter) {
        const lineCount = text.split("\n").length;
        let html = "";
        for (let i = 1; i <= lineCount; i++) html += `<span>${i}</span>`;
        gutter.innerHTML = html;
      }
      // resize:none hands height entirely to this — grow to fit content
      // exactly (no internal textarea scrollbar), so it's the *outer*
      // .ac-code-scroll wrapper that scrolls once things get long, with
      // the gutter and highlight overlay scrolling right along with it.
      // scrollHeight is meaningless while a display:none ancestor (a
      // still-closed modal, or the hidden Value/Script sub-field) hides
      // this — see the modal-open and kind-toggle listeners below, which
      // force a resync at the moment this actually becomes visible.
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;

      // Horizontal counterpart of the height auto-grow above: with wrap
      // disabled (see .ac-code-textarea's own comment on why), nothing
      // else makes this box — or the overlay stacked on top of it, sized
      // to match via inset: 0 — wide enough for its longest line. A
      // <textarea>'s own intrinsic width isn't driven by its content the
      // way a block of text is, so it's measured here instead, the same
      // "render off-screen and read scrollWidth" trick used for the
      // {{var}}-drift + wrap-divergence diagnosis that found this bug.
      if (inner && scroller) {
        const natural = measureNaturalTextWidth(textarea, text) + 24; // headroom so the last glyph isn't flush against the scroll edge
        const gutterWidth = gutter ? gutter.getBoundingClientRect().width : 0;
        const available = scroller.getBoundingClientRect().width - gutterWidth;
        inner.style.width = `${Math.max(natural, available)}px`;
      }
    }
    textarea.addEventListener("input", sync);
    sync();
  }

  const bodyField = document.querySelector("[data-ac-body]");
  attachCodeEditor(bodyField, () => detectBodyLanguage(currentHeaders(), bodyField ? bodyField.value : ""));

  // Content-Type drives the request body's highlighting language (see
  // detectBodyLanguage above) — since it's the "language" argument that
  // was passed to attachCodeEditor, not something that field's own
  // "input" event fires for, a header add/edit/remove has to explicitly
  // nudge the body editor to resync.
  function resyncBodyLanguage() {
    bodyField?.dispatchEvent(new Event("input"));
  }

  document.querySelector("[data-ac-add-header]")?.addEventListener("click", () => addHeaderRow("", ""));

  headersContainer?.addEventListener("click", (event) => {
    const removeBtn = event.target.closest("[data-ac-remove-header]");
    if (removeBtn) {
      removeBtn.closest("[data-ac-header-row]").remove();
      updateHeaderCount();
      resyncBodyLanguage();
      return;
    }
    const sensitiveBtn = event.target.closest("[data-ac-sensitive-toggle]");
    if (sensitiveBtn) {
      const isOn = sensitiveBtn.classList.toggle("is-on");
      // Inline style rather than trusting the stylesheet cascade: this
      // button already carries .btn.act.edit (3 classes), and a same-file
      // .is-on override needs equal-or-higher specificity to ever win, so
      // setting it directly here is the reliable path. Longhand
      // backgroundColor, not the background shorthand — setting the
      // shorthand to a bare var() doesn't reliably expand into
      // background-color across browsers.
      sensitiveBtn.style.backgroundColor = isOn ? "var(--warn-bg)" : "";
      sensitiveBtn.style.color = isOn ? "var(--warn)" : "";
    }
  });

  headersContainer?.addEventListener("input", (event) => {
    if (event.target.matches("[data-ac-header-key]")) updateHeaderCount();
    if (event.target.matches("[data-ac-header-key], [data-ac-header-value]")) resyncBodyLanguage();
  });

  function currentHeaders() {
    return headerRows()
      .map((row) => [
        row.querySelector("[data-ac-header-key]").value.trim(),
        row.querySelector("[data-ac-header-value]").value,
        row.querySelector("[data-ac-sensitive-toggle]").classList.contains("is-on") || SENSITIVE_HEADER_PATTERN.test(row.querySelector("[data-ac-header-key]").value),
      ])
      .filter(([key]) => key);
  }

  function currentPayload() {
    return {
      method: document.querySelector("[data-ac-method]").value,
      url: document.querySelector("[data-ac-url]").value,
      headers: currentHeaders().map(([k, v]) => [k, v]),
      body: document.querySelector("[data-ac-body]").value,
      collection_id: CURRENT.collection_id,
      request_id: CURRENT.id,
    };
  }

  // ── {{variable}} autocomplete ─────────────────────────────────────────────
  // Triggers in the URL bar, header key/value inputs, and the body textarea:
  // typing "{{" opens a filtered list of every variable visible from here
  // (collection-scoped listed first, matching real resolution precedence —
  // see the server-side `all_variables` ordering in the api_client router).
  const AC_SCOPE_LABEL = { collection: "collection", global: "global", builtin: "built-in" };
  const AC_FIELD_SELECTOR = "[data-ac-url], [data-ac-header-key], [data-ac-header-value], [data-ac-param-key], [data-ac-param-value], [data-ac-body]";

  let suggestBox = null;
  let suggestField = null;
  let suggestMatchStart = -1;
  let suggestItems = [];
  let suggestActiveIndex = -1;

  function ensureSuggestBox() {
    if (!suggestBox) {
      suggestBox = document.createElement("div");
      suggestBox.className = "ac-varsuggest";
      suggestBox.hidden = true;
      document.body.appendChild(suggestBox);
    }
    return suggestBox;
  }

  function closeSuggest() {
    if (suggestBox) suggestBox.hidden = true;
    suggestField = null;
    suggestMatchStart = -1;
    suggestItems = [];
    suggestActiveIndex = -1;
  }

  function renderSuggest() {
    const box = ensureSuggestBox();
    box.innerHTML = suggestItems.map((item, i) => `
      <div class="ac-varsuggest-item${i === suggestActiveIndex ? " is-active" : ""}" data-index="${i}">
        <span class="ac-varsuggest-name">{{${item.name}}}</span>
        <span class="ac-varsuggest-scope">${AC_SCOPE_LABEL[item.scope] || item.scope}</span>
        ${item.description ? `<span class="ac-varsuggest-desc"></span>` : ""}
      </div>`).join("");
    // Descriptions can contain arbitrary user text — set via textContent,
    // never interpolated into the innerHTML string above.
    box.querySelectorAll(".ac-varsuggest-desc").forEach((el, i) => {
      el.textContent = suggestItems[i].description;
    });
    const rect = suggestField.getBoundingClientRect();
    box.style.left = `${rect.left + window.scrollX}px`;
    box.style.top = `${rect.bottom + window.scrollY + 4}px`;
    box.style.minWidth = `${Math.min(320, Math.max(220, rect.width))}px`;
    box.hidden = false;
  }

  function checkForVarTrigger(field) {
    if (typeof field.selectionStart !== "number") return;
    const pos = field.selectionStart;
    const before = field.value.slice(0, pos);
    const match = before.match(/\{\{([a-zA-Z0-9_-]*)$/);
    if (!match) {
      closeSuggest();
      return;
    }
    const partial = match[1].toLowerCase();
    // Prefix hits first (typing "base_url" should still lead with
    // base_url_dev_tc), then anything that merely contains what was typed
    // (so "dev_tc" also turns up base_url_dev_tc) — best of both.
    const startsWithMatches = AC_VARIABLES.filter((v) => v.name.toLowerCase().startsWith(partial));
    const containsMatches = partial
      ? AC_VARIABLES.filter((v) => !v.name.toLowerCase().startsWith(partial) && v.name.toLowerCase().includes(partial))
      : [];
    const matches = [...startsWithMatches, ...containsMatches].slice(0, 8);
    if (!matches.length) {
      closeSuggest();
      return;
    }
    suggestField = field;
    suggestMatchStart = pos - match[0].length;
    suggestItems = matches;
    suggestActiveIndex = 0;
    renderSuggest();
  }

  function applySuggest(item) {
    if (!suggestField) return;
    const field = suggestField;
    const pos = field.selectionStart;
    const insertion = `{{${item.name}}}`;
    field.value = field.value.slice(0, suggestMatchStart) + insertion + field.value.slice(pos);
    const newPos = suggestMatchStart + insertion.length;
    field.selectionStart = field.selectionEnd = newPos;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    closeSuggest();
    field.focus();
  }

  document.addEventListener("input", (event) => {
    if (!event.target.matches || !event.target.matches(AC_FIELD_SELECTOR)) return;
    checkForVarTrigger(event.target);
  });

  document.addEventListener("keydown", (event) => {
    if (!suggestBox || suggestBox.hidden) return;
    if (event.key === "Escape") {
      closeSuggest();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      suggestActiveIndex = Math.min(suggestActiveIndex + 1, suggestItems.length - 1);
      renderSuggest();
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      suggestActiveIndex = Math.max(suggestActiveIndex - 1, 0);
      renderSuggest();
      return;
    }
    if (event.key === "Enter" || event.key === "Tab") {
      if (suggestActiveIndex >= 0 && suggestItems[suggestActiveIndex]) {
        event.preventDefault();
        applySuggest(suggestItems[suggestActiveIndex]);
      }
    }
  });

  document.addEventListener("mousedown", (event) => {
    const item = event.target.closest(".ac-varsuggest-item");
    if (item && suggestBox && !suggestBox.hidden) {
      event.preventDefault();
      const index = parseInt(item.dataset.index, 10);
      if (suggestItems[index]) applySuggest(suggestItems[index]);
      return;
    }
    if (suggestBox && !suggestBox.hidden && event.target !== suggestField) {
      closeSuggest();
    }
  });

  // ── Populate hidden fields before "Save" / "Save As" submits ────────────
  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (!form.querySelector("[data-ac-hidden-method]")) return;
    const payload = currentPayload();
    form.querySelector("[data-ac-hidden-method]").value = payload.method;
    form.querySelector("[data-ac-hidden-url]").value = payload.url;
    form.querySelector("[data-ac-hidden-headers]").value = JSON.stringify(payload.headers);
    form.querySelector("[data-ac-hidden-body]").value = payload.body;
  });

  // ── Autosave (already-saved requests only) ───────────────────────────────
  // A brand-new, never-saved request still goes through the "Save" modal
  // (it needs a name + a collection chosen, nothing to infer that from) —
  // but once it has an id, every further edit here debounces into a
  // background POST to the same edit route the manual Save button used,
  // same 700ms debounce + save-state-indicator pattern as the autosave
  // already used elsewhere in the app (see app.js's `submitAutosave`).
  (function initAutosave() {
    const editForm = document.getElementById("ac-edit-form");
    if (!editForm) return;

    // Visibility of the manual-save button / "Saved" label / "Save" (new)
    // link is owned by applyTabToDom (see "Request tabs" below) — it's the
    // one place that knows which tab is active, since that can now change
    // without a page reload. This IIFE only wires up autosave's behavior.
    const manualSaveBtn = document.querySelector("[data-ac-manual-save]");
    const stateEl = document.querySelector("[data-ac-save-state]");

    const SAVE_LABELS = { editing: "Unsaved changes", saving: "Saving…", saved: "Saved", error: "Not saved — retry" };
    function setState(state) {
      if (!stateEl) return;
      stateEl.textContent = SAVE_LABELS[state] || "";
      stateEl.dataset.state = state;
    }

    async function saveNow() {
      if (!CURRENT.id) return; // active tab is an unsaved "New Request" — nothing to autosave to
      setState("saving");
      const payload = currentPayload();
      const body = new FormData();
      body.append("name", CURRENT.name);
      body.append("method", payload.method);
      body.append("url", payload.url);
      body.append("headers_json", JSON.stringify(payload.headers));
      body.append("body", payload.body);
      try {
        const response = await fetch(editForm.action, { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
        setState(response.ok ? "saved" : "error");
      } catch {
        setState("error");
      }
    }

    let timer;
    function scheduleSave() {
      if (!CURRENT.id || applyingTab) return;
      setState("editing");
      clearTimeout(timer);
      timer = setTimeout(saveNow, 700);
    }

    document.addEventListener("input", (event) => {
      if (event.target.matches("[data-ac-method], [data-ac-url], [data-ac-header-key], [data-ac-header-value], [data-ac-body]")) {
        scheduleSave();
      }
    });
    document.addEventListener("change", (event) => {
      if (event.target.matches("[data-ac-method]")) scheduleSave();
    });
    document.addEventListener("click", (event) => {
      if (event.target.closest("[data-ac-add-header], [data-ac-remove-header], [data-ac-sensitive-toggle]")) {
        scheduleSave();
      }
    });
    // Don't lose the last keystroke if the tab closes mid-debounce.
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden" && stateEl?.dataset.state === "editing") {
        clearTimeout(timer);
        saveNow();
      }
    });
  })();

  // ── Paste-a-curl auto-fill ────────────────────────────────────────────────
  // applyParsedCurl fills the live builder from an already-parsed
  // /parse-curl response; shared by the paste handler below and by
  // autoFixSavedCurlUrl (self-heals a request whose saved `url` is itself
  // a raw curl string — see that function for why that can happen).
  function applyParsedCurl(data) {
    document.querySelector("[data-ac-method]").value = data.method;
    const urlField = document.querySelector("[data-ac-url]");
    urlField.value = data.url;
    headersContainer.innerHTML = "";
    (data.headers || []).forEach(([k, v]) => addHeaderRow(k, v));
    const bodyField = document.querySelector("[data-ac-body]");
    bodyField.value = data.body || "";
    // Params/Headers/Body are always shown at once now (no tabs to switch
    // to) — just make sure the URL bar's {{var}} highlight overlay and the
    // body's syntax-highlight overlay + gutter resync, since setting .value
    // directly doesn't fire "input" on its own (both real fields render
    // transparent text over an overlay div that only repaints on "input" —
    // skipping this leaves the address bar looking blank even though its
    // value is set correctly underneath).
    urlField.dispatchEvent(new Event("input", { bubbles: true }));
    bodyField.dispatchEvent(new Event("input", { bubbles: true }));
  }

  const urlInput = document.querySelector("[data-ac-url]");
  urlInput?.addEventListener("paste", async (event) => {
    const text = (event.clipboardData || window.clipboardData).getData("text");
    if (!/^\s*curl\b/i.test(text || "")) return;
    event.preventDefault();
    try {
      const response = await fetch("/api-client/parse-curl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await response.json();
      if (!data.matched) {
        urlInput.value = text;
        urlInput.dispatchEvent(new Event("input", { bubbles: true }));
        return;
      }
      applyParsedCurl(data);
      toast("Parsed from curl");
    } catch {
      urlInput.value = text;
      urlInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
  });

  // ── Self-heal a saved request whose URL is itself a raw curl string ─────
  // Before the quick "New Request" modals had their own curl-paste
  // handling, pasting a curl there saved it verbatim as the URL — so a
  // request created that way looks broken every single time it's opened,
  // not just once. Anything already saved that way gets parsed right on
  // load, same as a fresh paste, and the corrected fields are written back
  // so this only has to happen once per request.
  async function autoFixSavedCurlUrl() {
    if (!urlInput || !/^\s*curl\b/i.test(urlInput.value || "")) return;
    try {
      const response = await fetch("/api-client/parse-curl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: urlInput.value }),
      });
      const data = await response.json();
      if (!data.matched) return;
      applyParsedCurl(data);
      toast("This saved request's URL was still a raw curl command — parsed it into Method/Headers/Body");

      const editForm = document.getElementById("ac-edit-form");
      if (editForm) {
        const payload = currentPayload();
        editForm.querySelector("[data-ac-hidden-method]").value = payload.method;
        editForm.querySelector("[data-ac-hidden-url]").value = payload.url;
        editForm.querySelector("[data-ac-hidden-headers]").value = JSON.stringify(payload.headers);
        editForm.querySelector("[data-ac-hidden-body]").value = payload.body;
        await fetch(editForm.action, { method: "POST", body: new FormData(editForm) });
      }
    } catch {
      // Leave the raw curl text in place — paste-to-fix still works by hand.
    }
  }
  autoFixSavedCurlUrl();

  // ── Query Params, kept in sync with the URL bar's own query string ──────
  // Not a separate field of its own — the URL bar is still the one source
  // of truth that actually gets sent. This is a two-way convenience view
  // on top of it: editing a param row rewrites the URL bar's query string,
  // and editing the query string directly (typing, paste, curl-parse,
  // restoring from history) re-parses back into rows. `syncingParams`
  // stops the two directions from ping-ponging off each other.
  const paramsContainer = document.querySelector("[data-ac-params]");
  const paramCount = document.querySelector("[data-ac-param-count]");
  let syncingParams = false;

  function splitUrl(url) {
    const qIndex = url.indexOf("?");
    return qIndex === -1 ? { base: url, query: "" } : { base: url.slice(0, qIndex), query: url.slice(qIndex + 1) };
  }

  function parseQueryString(query) {
    if (!query) return [];
    return query.split("&").filter(Boolean).map((pair) => {
      const eq = pair.indexOf("=");
      if (eq === -1) return [safeDecodeURIComponent(pair), ""];
      return [safeDecodeURIComponent(pair.slice(0, eq)), safeDecodeURIComponent(pair.slice(eq + 1))];
    });
  }

  // A param's value is often itself a {{variable}}, and decodeURIComponent
  // throws on a lone "%" (e.g. a stray "%" typed mid-edit, before it's a
  // full percent-escape) — fall back to the raw text rather than losing
  // the row entirely over an incomplete edit.
  function safeDecodeURIComponent(s) {
    try {
      return decodeURIComponent(s);
    } catch {
      return s;
    }
  }

  function paramRows() {
    return paramsContainer ? Array.from(paramsContainer.querySelectorAll("[data-ac-param-row]")) : [];
  }

  function currentParams() {
    return paramRows().map((row) => [
      row.querySelector("[data-ac-param-key]").value,
      row.querySelector("[data-ac-param-value]").value,
    ]);
  }

  function buildQueryString(params) {
    return params
      .filter(([k]) => k)
      .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
      .join("&");
  }

  function updateParamCount() {
    if (!paramCount) return;
    const filled = paramRows().filter((row) => row.querySelector("[data-ac-param-key]").value.trim()).length;
    paramCount.textContent = String(filled);
  }

  function addParamRow(key, value) {
    if (!paramsContainer) return;
    const row = document.createElement("tr");
    row.setAttribute("data-ac-param-row", "");
    row.innerHTML = `
      <td><input class="ac-kv-key" data-ac-param-key placeholder="Key" value="${escapeAttr(key || "")}"></td>
      <td><input data-ac-param-value placeholder="Value" value="${escapeAttr(value || "")}"></td>
      <td class="ac-kv-actions">
        <button type="button" class="btn act remove" data-ac-remove-param title="Remove param" aria-label="Remove param">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>
        </button>
      </td>`;
    paramsContainer.appendChild(row);
    initVariableHighlighting(row);
    updateParamCount();
    return row;
  }

  function syncParamsFromUrl() {
    if (syncingParams || !paramsContainer || !urlInput) return;
    syncingParams = true;
    const parsed = parseQueryString(splitUrl(urlInput.value).query);
    paramsContainer.innerHTML = "";
    parsed.forEach(([k, v]) => addParamRow(k, v));
    if (!parsed.length) addParamRow("", "");
    syncingParams = false;
  }

  function syncUrlFromParams() {
    if (syncingParams || !urlInput) return;
    syncingParams = true;
    const { base } = splitUrl(urlInput.value);
    const qs = buildQueryString(currentParams());
    urlInput.value = qs ? `${base}?${qs}` : base;
    // Re-triggers the URL bar's own {{var}} highlight overlay and the
    // autosave debounce — not a second params resync, syncingParams is
    // still true for the rest of this synchronous call.
    urlInput.dispatchEvent(new Event("input", { bubbles: true }));
    syncingParams = false;
  }

  document.querySelector("[data-ac-add-param]")?.addEventListener("click", () => {
    addParamRow("", "");
    syncUrlFromParams();
  });

  paramsContainer?.addEventListener("click", (event) => {
    const removeBtn = event.target.closest("[data-ac-remove-param]");
    if (!removeBtn) return;
    removeBtn.closest("[data-ac-param-row]").remove();
    if (!paramRows().length) addParamRow("", "");
    updateParamCount();
    syncUrlFromParams();
  });

  paramsContainer?.addEventListener("input", (event) => {
    if (!event.target.matches("[data-ac-param-key], [data-ac-param-value]")) return;
    updateParamCount();
    syncUrlFromParams();
  });

  urlInput?.addEventListener("input", syncParamsFromUrl);
  syncParamsFromUrl();

  // Same curl-paste auto-fill, but for the quick "New Request" modals' plain
  // URL field — those only have Name/Method/URL visible, so headers/body
  // land in hidden inputs (still submitted, just edited later in the full
  // builder). Delegated on document since a modal per collection/folder
  // means many of these fields exist at once, all created at render time.
  document.addEventListener("paste", async (event) => {
    const target = event.target;
    if (!target.matches || !target.matches("[data-ac-quickcreate-url]")) return;
    const text = (event.clipboardData || window.clipboardData).getData("text");
    if (!/^\s*curl\b/i.test(text || "")) return;
    event.preventDefault();
    const form = target.closest("form");
    try {
      const response = await fetch("/api-client/parse-curl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const data = await response.json();
      if (!data.matched) {
        target.value = text;
        return;
      }
      const methodField = form.querySelector("[data-ac-quickcreate-method]");
      if (methodField) methodField.value = data.method;
      target.value = data.url;
      const headersField = form.querySelector("[data-ac-quickcreate-headers]");
      if (headersField) headersField.value = JSON.stringify(data.headers || []);
      const bodyField = form.querySelector("[data-ac-quickcreate-body]");
      if (bodyField) bodyField.value = data.body || "";
      toast("Parsed from curl");
    } catch {
      target.value = text;
    }
  });

  // ── Send ──────────────────────────────────────────────────────────────────
  const sendBtn = document.querySelector("[data-ac-send]");
  const responseEmpty = document.querySelector("[data-ac-response-empty]");
  const responseBox = document.querySelector("[data-ac-response]");
  let lastSensitiveValues = [];

  function statusPillClass(status) {
    if (!status) return "is-fail";
    return status >= 200 && status < 400 ? "" : "is-fail";
  }

  function renderResponse(data, fromHistory) {
    responseEmpty.hidden = true;
    responseBox.hidden = false;
    lastSensitiveValues = data.sensitive_values || [];

    const historyNote = fromHistory
      ? `<p class="ac-hint">
           <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/></svg>
           Showing the last time this ran &mdash; hit Send for a fresh result.
         </p>`
      : "";

    if (data.error) {
      responseBox.innerHTML = `
        ${historyNote}
        <div class="ac-report-section-head">
          <span class="card-title">Response</span>
          <span class="ac-status-pill is-fail">Request failed</span>
        </div>
        <p class="muted" style="font-family: var(--font-mono); font-size: 12.5px;">${escapeHtml(data.error)}</p>`;
      return;
    }

    const unresolvedNote = (data.unresolved && data.unresolved.length)
      ? `<p class="ac-hint" style="color: var(--warn);">Unresolved: ${data.unresolved.map(escapeHtml).join(", ")}</p>`
      : "";

    const lines = (data.body || "").split("\n");
    const gutter = lines.map((_, i) => `<span>${i + 1}</span>`).join("");
    const lang = detectBodyLanguage(data.headers, data.body);
    const contentType = (data.headers || []).find(([k]) => k.toLowerCase() === "content-type");

    responseBox.innerHTML = `
      ${historyNote}
      <div class="ac-report-section-head">
        <span class="card-title">Response</span>
        <div class="ac-resp-status-row" style="margin-bottom: 0;">
          <span class="ac-status-pill ${statusPillClass(data.status)}">${data.status || "—"}</span>
          <span class="ac-stat-chip">${data.duration_ms} ms</span>
          <span class="ac-stat-chip">${formatSize(data.size_bytes)}</span>
        </div>
      </div>
      ${unresolvedNote}
      <div class="ac-report-subhead ac-report-subhead-row">
        <span class="ac-report-subhead-title">Response Payload <span class="badge code">${escapeHtml(contentType ? contentType[1] : "n/a")}</span></span>
        <div style="display: flex; gap: 6px;">
          <button type="button" class="btn act edit" data-ac-copy-response title="Copy response body" aria-label="Copy response body">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          </button>
          <button type="button" class="btn act edit" data-ac-wrap-toggle title="Wrap long lines" aria-label="Wrap long lines">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18M3 12h13a3 3 0 0 1 0 6h-4m0 0 3-3m-3 3 3 3M3 18h4"/></svg>
          </button>
        </div>
      </div>
      <div class="code-block">
        <div class="snippet-code ac-code-scroll">
          <div class="snippet-gutter">${gutter}</div>
          <pre class="snippet-pre" data-ac-response-pre><code data-snippet-code="${lang}">${escapeHtml(data.body || "")}</code></pre>
        </div>
      </div>
      <div class="ac-collapsible">
        <button type="button" class="ac-report-subhead ac-collapsible-summary" data-ac-headers-toggle><span class="ac-chev">${CHEVRON_SVG}</span>Response Headers</button>
        <div class="ac-report-table-wrap" hidden>
          <table class="ac-report-table">
            <thead><tr><th>HEADER</th><th>VALUE</th></tr></thead>
            <tbody>
              ${(data.headers || []).map(([k, v]) => `<tr><td>${escapeHtml(k)}</td><td>${escapeHtml(v)}</td></tr>`).join("")}
            </tbody>
          </table>
        </div>
      </div>`;

    responseBox.querySelector("[data-ac-headers-toggle]")?.addEventListener("click", (event) => {
      const wrap = event.currentTarget.closest(".ac-collapsible");
      const table = wrap.querySelector(".ac-report-table-wrap");
      table.hidden = !table.hidden;
      wrap.classList.toggle("is-open", !table.hidden);
    });

    if (window.hljs) {
      responseBox.querySelectorAll("[data-snippet-code]").forEach((block) => {
        block.classList.add(`language-${block.dataset.snippetCode}`);
        window.hljs.highlightElement(block);
      });
    }

    const wrapToggle = responseBox.querySelector("[data-ac-wrap-toggle]");
    const responsePre = responseBox.querySelector("[data-ac-response-pre]");
    function applyWrap(on) {
      if (responsePre) responsePre.classList.toggle("is-wrapped", on);
      if (wrapToggle) wrapToggle.classList.toggle("is-active", on);
    }
    let wrapOn = false;
    try { wrapOn = localStorage.getItem(WRAP_KEY) === "1"; } catch { /* storage unavailable */ }
    applyWrap(wrapOn);
    wrapToggle?.addEventListener("click", () => {
      wrapOn = !wrapOn;
      applyWrap(wrapOn);
      try { localStorage.setItem(WRAP_KEY, wrapOn ? "1" : "0"); } catch { /* storage unavailable */ }
    });

    responseBox.querySelector("[data-ac-copy-response]")?.addEventListener("click", async () => {
      await copyText(data.body || "");
      toast("Response copied");
    });
  }

  // Opening a saved request shows its last real hit (from History) rather
  // than an empty panel, so the response area isn't blank just because you
  // navigated here instead of clicking Send — server sends it pre-fetched
  // (see the `builder` route's `last_response`) so this is a plain render,
  // no extra round trip.
  if (window.__AC_LAST_RESPONSE__) {
    renderResponse(window.__AC_LAST_RESPONSE__, true);
  }

  function formatSize(bytes) {
    if (bytes === undefined || bytes === null) return "—";
    if (bytes < 1024) return `${bytes} B`;
    return `${(bytes / 1024).toFixed(1)} KB`;
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
  }

  sendBtn?.addEventListener("click", async () => {
    sendBtn.disabled = true;
    const originalHtml = sendBtn.innerHTML;
    sendBtn.textContent = "Sending…";
    try {
      const response = await fetch("/api-client/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentPayload()),
      });
      const data = await response.json();
      renderResponse(data);
    } catch (err) {
      renderResponse({ error: `Network error: ${err}` });
    } finally {
      sendBtn.disabled = false;
      sendBtn.innerHTML = originalHtml;
    }
  });

  // ── Copy as cURL ──────────────────────────────────────────────────────────
  document.querySelector("[data-ac-copy-curl]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    try {
      const response = await fetch("/api-client/resolve", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(currentPayload()),
      });
      const data = await response.json();
      await copyText(data.curl);
      toast("curl copied");
    } catch {
      toast("Couldn't build the curl command", "danger");
    }
  });

  // ── Export image (download + copy to clipboard) ──────────────────────────
  // Renders via html2canvas (vendored — see
  // app/static/js/vendor/html2canvas/README.md for why: an earlier
  // hand-rolled SVG-<foreignObject>-to-canvas version always failed with
  // "Tainted canvases may not be exported" — Chrome taints any canvas
  // drawn from an SVG containing foreignObject on principle, same-origin
  // or not. html2canvas repaints the DOM with canvas primitives instead of
  // rasterizing an image, so the canvas is never "tainted" in the first
  // place.
  //
  // Always renders a CLONE, never the live DOM. cloneNode(true) only
  // copies each input/select/textarea's original value/selected
  // ATTRIBUTE, not whatever's actually been typed or selected since —
  // copyLiveFormValues corrects that before anything is masked or drawn.
  function copyLiveFormValues(sourceRoot, cloneRoot) {
    const srcFields = sourceRoot.querySelectorAll("input, textarea, select");
    const dstFields = cloneRoot.querySelectorAll("input, textarea, select");
    srcFields.forEach((src, i) => {
      if (dstFields[i]) dstFields[i].value = src.value;
    });
  }

  function maskSensitiveValues(cloneRoot, maskValues) {
    const values = maskValues.filter(Boolean);
    if (!values.length) return;
    const walker = document.createTreeWalker(cloneRoot, NodeFilter.SHOW_TEXT);
    const textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach((node) => {
      let text = node.nodeValue;
      let changed = false;
      values.forEach((value) => {
        if (text.includes(value)) {
          text = text.split(value).join("••••••••");
          changed = true;
        }
      });
      if (changed) node.nodeValue = text;
    });
    cloneRoot.querySelectorAll("input, textarea").forEach((el) => {
      let value = el.value;
      values.forEach((v) => {
        if (value && value.includes(v)) value = value.split(v).join("••••••••");
      });
      el.value = value;
    });
  }

  // A long request body or response is internally scrolled on the live
  // page (see .ac-code-scroll) — for an export that's wrong, it would
  // silently crop out whatever's currently scrolled out of view. The
  // clone gets its scroll caps lifted first so html2canvas captures the
  // whole thing at full height instead of just the visible window.
  function expandScrollCaps(cloneRoot) {
    cloneRoot.querySelectorAll(".ac-code-scroll").forEach((el) => {
      el.style.maxHeight = "none";
      el.style.overflow = "visible";
    });
  }

  let lastExportUrl = null;

  document.querySelector("[data-ac-export-image]")?.addEventListener("click", async () => {
    if (!window.html2canvas) {
      toast("Image export isn't available (html2canvas failed to load)", "danger");
      return;
    }
    const topbar = document.querySelector("[data-ac-topbar]");
    const requestCard = document.querySelector("[data-ac-request-card]");
    const responsePanel = document.querySelector("[data-ac-response-panel]");
    if (!responseBox || responseBox.hidden) {
      toast("Send the request first", "danger");
      return;
    }

    const topbarClone = topbar.cloneNode(true);
    const requestClone = requestCard.cloneNode(true);
    const responseClone = responsePanel.cloneNode(true);
    copyLiveFormValues(topbar, topbarClone);
    copyLiveFormValues(requestCard, requestClone);
    copyLiveFormValues(responsePanel, responseClone);
    expandScrollCaps(requestClone);
    expandScrollCaps(responseClone);

    const maskValues = [...lastSensitiveValues];
    headerRows().forEach((row) => {
      if (row.querySelector("[data-ac-sensitive-toggle]").classList.contains("is-on")) {
        maskValues.push(row.querySelector("[data-ac-header-value]").value);
      }
    });
    maskSensitiveValues(requestClone, maskValues);
    maskSensitiveValues(responseClone, maskValues);

    const columns = document.createElement("div");
    columns.style.cssText = "display:flex;gap:18px;align-items:flex-start;";
    columns.style.width = `${Math.max(requestCard.offsetWidth, responsePanel.offsetWidth) * 2 + 18}px`;
    requestClone.style.flex = "1 1 0";
    responseClone.style.flex = "1 1 0";
    columns.appendChild(requestClone);
    columns.appendChild(responseClone);

    const wrapper = document.createElement("div");
    wrapper.style.cssText = "display:flex;flex-direction:column;gap:18px;padding:18px;background:#faf9f5;position:fixed;left:-99999px;top:0;";
    wrapper.appendChild(topbarClone);
    wrapper.appendChild(columns);
    document.body.appendChild(wrapper);

    const modal = document.getElementById("export-image-preview");
    const statusEl = modal.querySelector("[data-ac-export-status]");
    const previewImg = modal.querySelector("[data-ac-export-preview-img]");

    try {
      const canvas = await window.html2canvas(wrapper, { backgroundColor: "#faf9f5", scale: 2 });
      const blob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));
      if (!blob) throw new Error("canvas.toBlob returned null");

      if (lastExportUrl) URL.revokeObjectURL(lastExportUrl);
      lastExportUrl = URL.createObjectURL(blob);
      previewImg.src = lastExportUrl;

      openModal(modal, document.querySelector("[data-ac-export-image]"));

      try {
        await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
        statusEl.textContent = "Copied to clipboard — paste it anywhere.";
      } catch {
        statusEl.textContent = "Couldn't copy automatically — use Copy Again below.";
      }

      modal.querySelector("[data-ac-export-download]").onclick = () => {
        const link = document.createElement("a");
        link.href = lastExportUrl;
        link.download = `api-client-${Date.now()}.png`;
        document.body.appendChild(link);
        link.click();
        link.remove();
      };
      modal.querySelector("[data-ac-export-copy-again]").onclick = async () => {
        try {
          await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
          toast("Image copied to clipboard");
        } catch {
          toast("Clipboard copy not available here", "danger");
        }
      };
    } catch (err) {
      console.error("Export image failed:", err);
      toast("Couldn't render the image", "danger");
    } finally {
      wrapper.remove();
    }
  });

  // ── Request tabs ──────────────────────────────────────────────────────────
  // Lets several requests stay open at once and switches between them
  // entirely client-side (no reload), so in-progress edits in a tab you're
  // not looking at aren't lost. The open set + which one's active persists
  // in localStorage (the qa-toolbox: convention used elsewhere — see
  // app.js's sidebar-collapsed key) so it survives navigating away to
  // History/Variables and back.
  //
  // A tab isn't the same thing as a saved ApiRequest row: it's a snapshot
  // of everything the request bar/panel would show (method, url, headers,
  // body, last response), tied to a requestId only once that snapshot has
  // actually been saved. Sending, and the server-side resolution of
  // {{variables}}, are entirely unaffected — they already work off
  // whatever's currently in the DOM (currentPayload()); tabs just decide
  // what that DOM contains at any given moment.
  (function initRequestTabs() {
    const stripEl = document.querySelector("[data-ac-request-tabs]");
    if (!stripEl) return; // not on the Builder page

    const TABS_KEY = "qa-toolbox:api-client-tabs";
    const SAVING_MARKER_KEY = "qa-toolbox:api-client-saving-tab";

    function loadStore() {
      try {
        const raw = localStorage.getItem(TABS_KEY);
        const parsed = raw ? JSON.parse(raw) : null;
        if (parsed && Array.isArray(parsed.tabs)) return parsed;
      } catch {
        /* corrupt or storage unavailable — start fresh */
      }
      return { tabs: [], activeClientId: null };
    }

    const store = loadStore();
    const tabs = store.tabs;
    let activeClientId = store.activeClientId;

    function persist() {
      try {
        localStorage.setItem(TABS_KEY, JSON.stringify({ tabs, activeClientId }));
      } catch {
        /* storage unavailable — tabs just won't survive navigating away */
      }
    }

    function newClientId() {
      return `t${Date.now().toString(36)}${Math.random().toString(36).slice(2, 7)}`;
    }

    function tabFromCurrent(current, lastResponse) {
      return {
        clientId: newClientId(),
        requestId: current.id ?? null,
        name: current.name || "New Request",
        method: current.method || "GET",
        url: current.url || "",
        headers: current.headers || [],
        body: current.body || "",
        collectionId: current.collection_id ?? null,
        lastResponse: lastResponse || null,
      };
    }

    function blankTab() {
      return tabFromCurrent({ id: null, name: "New Request", method: "GET", url: "", headers: [], body: "", collection_id: null });
    }

    function findByClientId(id) {
      return tabs.find((t) => t.clientId === id);
    }
    function findByRequestId(id) {
      return id ? tabs.find((t) => t.requestId === id) : undefined;
    }
    function activeTab() {
      return findByClientId(activeClientId) || tabs[0] || null;
    }

    // ── DOM <-> tab state ─────────────────────────────────────────────────
    function captureIntoActiveTab() {
      const tab = activeTab();
      if (!tab) return;
      const payload = currentPayload();
      tab.method = payload.method;
      tab.url = payload.url;
      tab.headers = payload.headers;
      tab.body = payload.body;
    }

    function applyTabToDom(tab) {
      applyingTab = true;
      CURRENT.id = tab.requestId;
      CURRENT.name = tab.name;
      CURRENT.collection_id = tab.collectionId;

      document.querySelector("[data-ac-method]").value = tab.method;
      const urlField = document.querySelector("[data-ac-url]");
      urlField.value = tab.url;
      urlField.dispatchEvent(new Event("input", { bubbles: true }));

      headersContainer.innerHTML = "";
      tab.headers.forEach(([k, v]) => addHeaderRow(k, v));

      const bodyField = document.querySelector("[data-ac-body]");
      bodyField.value = tab.body;
      bodyField.dispatchEvent(new Event("input", { bubbles: true }));
      applyingTab = false;

      const nameEl = document.querySelector("[data-ac-current-name]");
      if (nameEl) nameEl.textContent = tab.name;

      // Which "Save" affordance shows (new-request modal link vs. the
      // already-saved autosave label) and where the hidden edit form
      // actually posts both depend on whether THIS tab has a requestId —
      // baked in once per page load before tabs existed, now decided here
      // on every switch instead.
      const editForm = document.getElementById("ac-edit-form");
      const saveNewLink = document.querySelector("[data-ac-save-new]");
      const manualSaveBtn = document.querySelector("[data-ac-manual-save]");
      const stateEl = document.querySelector("[data-ac-save-state]");
      if (tab.requestId) {
        if (editForm) editForm.action = `/api-client/requests/${tab.requestId}/edit`;
        if (saveNewLink) saveNewLink.hidden = true;
        if (manualSaveBtn) manualSaveBtn.hidden = true;
        if (stateEl) {
          stateEl.hidden = false;
          stateEl.textContent = "Saved";
          stateEl.dataset.state = "saved";
        }
      } else {
        if (editForm) editForm.action = "";
        if (saveNewLink) saveNewLink.hidden = false;
        if (manualSaveBtn) manualSaveBtn.hidden = true;
        if (stateEl) stateEl.hidden = true;
      }

      if (tab.lastResponse) {
        renderResponse(tab.lastResponse, true);
      } else {
        responseBox.hidden = true;
        responseBox.innerHTML = "";
        responseEmpty.hidden = false;
      }
    }

    // ── Tab strip ─────────────────────────────────────────────────────────
    function renderStrip() {
      stripEl.innerHTML = "";
      tabs.forEach((tab) => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "ac-request-tab" + (tab.clientId === activeClientId ? " is-active" : "");
        btn.dataset.acTabId = tab.clientId;
        btn.innerHTML = `
          <span class="ac-method-badge m-${escapeAttr(tab.method.toLowerCase())}">${escapeHtml(tab.method)}</span>
          <span class="ac-request-tab-name">${escapeHtml(tab.name)}</span>
          <span class="ac-request-tab-close" data-ac-tab-close title="Close" aria-label="Close ${escapeHtml(tab.name)}">&times;</span>
        `;
        stripEl.appendChild(btn);
      });
      const addBtn = document.createElement("button");
      addBtn.type = "button";
      addBtn.className = "ac-request-tab-add";
      addBtn.dataset.acTabAdd = "";
      addBtn.title = "New tab";
      addBtn.setAttribute("aria-label", "New tab");
      addBtn.textContent = "+";
      stripEl.appendChild(addBtn);
    }

    function switchTo(clientId) {
      if (clientId === activeClientId) return;
      captureIntoActiveTab();
      activeClientId = clientId;
      renderStrip();
      applyTabToDom(activeTab());
      persist();
    }

    // Keep the active tab's localStorage snapshot current as you type —
    // not just at switch/close time — otherwise a plain page reload (e.g.
    // re-opening the same ?request_id= link, or navigating away and back)
    // would restore the stale snapshot from whenever a tab last changed
    // focus and clobber whatever autosave had since persisted server-side.
    let syncTimer;
    function scheduleTabSync() {
      if (applyingTab) return;
      clearTimeout(syncTimer);
      syncTimer = setTimeout(() => {
        captureIntoActiveTab();
        persist();
      }, 400);
    }
    document.addEventListener("input", (event) => {
      if (event.target.matches("[data-ac-method], [data-ac-url], [data-ac-header-key], [data-ac-header-value], [data-ac-body]")) {
        scheduleTabSync();
      }
    });
    document.addEventListener("change", (event) => {
      if (event.target.matches("[data-ac-method]")) scheduleTabSync();
    });
    document.addEventListener("click", (event) => {
      if (event.target.closest("[data-ac-add-header], [data-ac-remove-header], [data-ac-sensitive-toggle]")) {
        scheduleTabSync();
      }
    });

    stripEl.addEventListener("click", (event) => {
      if (event.target.closest("[data-ac-tab-add]")) {
        captureIntoActiveTab();
        const tab = blankTab();
        tabs.push(tab);
        activeClientId = tab.clientId;
        renderStrip();
        applyTabToDom(tab);
        persist();
        document.querySelector("[data-ac-url]")?.focus();
        return;
      }
      const closeBtn = event.target.closest("[data-ac-tab-close]");
      if (closeBtn) {
        event.stopPropagation();
        const tabBtn = closeBtn.closest("[data-ac-tab-id]");
        const clientId = tabBtn?.dataset.acTabId;
        const index = tabs.findIndex((t) => t.clientId === clientId);
        if (index === -1) return;
        tabs.splice(index, 1);
        if (!tabs.length) tabs.push(blankTab());
        if (activeClientId === clientId) {
          const next = tabs[Math.min(index, tabs.length - 1)];
          activeClientId = next.clientId;
          applyTabToDom(next);
        }
        renderStrip();
        persist();
        return;
      }
      const tabBtn = event.target.closest("[data-ac-tab-id]");
      if (tabBtn) switchTo(tabBtn.dataset.acTabId);
    });

    // A save through the "Save Request" modal (POST /api-client/requests)
    // is the one thing that still reloads the page: it needs a name and a
    // collection chosen, nothing here to infer either from. Stash which tab
    // was mid-save so the reload can update that same tab in place instead
    // of opening a second, duplicate one for what's now the same request.
    document.getElementById("save-request")?.addEventListener("submit", () => {
      // Force the just-typed fields into this tab's localStorage snapshot
      // right now, synchronously — the debounced sync (scheduleTabSync)
      // might not have fired yet, and the page is about to navigate away
      // to the newly-saved request. Without this, the reload could
      // reconcile onto a stale (e.g. still-blank) snapshot, and the
      // replay-triggered autosave 700ms later would then push that stale
      // data back over the save that was just made.
      captureIntoActiveTab();
      persist();
      try {
        sessionStorage.setItem(SAVING_MARKER_KEY, activeClientId || "");
      } catch {
        /* storage unavailable — worst case, saving opens a second tab */
      }
    });

    // Keep every tab's own memory of "what it last showed" in sync,
    // whether that's a fresh Send or the page's initial replay of the last
    // real hit — wrapping here covers both without duplicating the logic
    // at each call site.
    const originalRenderResponse = renderResponse;
    renderResponse = function (data, fromHistory) {
      originalRenderResponse(data, fromHistory);
      const tab = activeTab();
      if (tab) tab.lastResponse = data;
    };

    // ── Resolve this page load into a tab ──────────────────────────────────
    const params = new URLSearchParams(location.search);
    if (params.has("request_id") || params.has("restore_history_id")) {
      let savingMarker = null;
      try {
        savingMarker = sessionStorage.getItem(SAVING_MARKER_KEY);
        sessionStorage.removeItem(SAVING_MARKER_KEY);
      } catch {
        /* ignore */
      }

      let tab = null;
      if (savingMarker) {
        const marked = findByClientId(savingMarker);
        if (marked && !marked.requestId) {
          marked.requestId = CURRENT.id;
          marked.name = CURRENT.name;
          tab = marked;
        }
      }
      if (!tab && params.has("request_id")) {
        tab = findByRequestId(CURRENT.id);
        if (tab) tab.name = CURRENT.name; // pick up a rename, keep any in-flight edits
      }
      if (!tab) {
        tab = tabFromCurrent(CURRENT, window.__AC_LAST_RESPONSE__);
        tabs.push(tab);
      }
      activeClientId = tab.clientId;
      // Drop the query string so a refresh restores from localStorage
      // instead of re-running this branch (and re-adding a tab) every time.
      history.replaceState(null, "", "/api-client");
    } else if (!tabs.length) {
      const tab = tabFromCurrent(CURRENT, window.__AC_LAST_RESPONSE__);
      tabs.push(tab);
      activeClientId = tab.clientId;
    } else if (!findByClientId(activeClientId)) {
      activeClientId = tabs[0].clientId;
    }

    renderStrip();
    applyTabToDom(activeTab());
    persist();
  })();
})();
