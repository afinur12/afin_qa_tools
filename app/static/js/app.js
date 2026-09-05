// ── Styled confirm dialog (replaces window.confirm on [data-confirm] forms) ─
let pendingConfirmForm = null;

function openConfirmDialog(message, form) {
  const dialog = document.getElementById("confirm-dialog");
  if (!dialog) {
    form.submit(); // no dialog markup on the page — degrade to submitting directly
    return;
  }
  dialog.querySelector("[data-confirm-message]").textContent = message;
  pendingConfirmForm = form;
  dialog.hidden = false;
  document.body.style.overflow = "hidden";
  dialog.querySelector("[data-confirm-ok]").focus();
}

function closeConfirmDialog() {
  const dialog = document.getElementById("confirm-dialog");
  if (dialog) {
    dialog.hidden = true;
    document.body.style.overflow = "";
  }
  pendingConfirmForm = null;
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!form.matches("[data-confirm]")) return;
  if (form.dataset.confirmed === "true") return; // already approved — let it through
  event.preventDefault();
  openConfirmDialog(form.dataset.confirm, form);
});

document.addEventListener("click", (event) => {
  if (event.target.closest("[data-confirm-ok]")) {
    const form = pendingConfirmForm;
    closeConfirmDialog();
    if (form) {
      form.dataset.confirmed = "true";
      if (form.requestSubmit) form.requestSubmit();
      else form.submit();
    }
    return;
  }
  if (event.target.closest("[data-confirm-cancel]")) {
    closeConfirmDialog();
    return;
  }
  if (event.target.id === "confirm-dialog") closeConfirmDialog();
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const dialog = document.getElementById("confirm-dialog");
  if (dialog && !dialog.hidden) closeConfirmDialog();
});

// ── Flash toast (a one-shot cookie set by the server on a redirect) ─────────
(function showFlashToast() {
  const flashMatch = document.cookie.match(/(?:^|; )flash=([^;]*)/);
  if (!flashMatch) return;
  const typeMatch = document.cookie.match(/(?:^|; )flash_type=([^;]*)/);

  document.cookie = "flash=; Max-Age=0; path=/";
  document.cookie = "flash_type=; Max-Age=0; path=/";

  const toast = document.createElement("div");
  toast.className = `toast toast--${typeMatch ? typeMatch[1] : "success"}`;
  toast.setAttribute("role", "status");
  toast.textContent = decodeURIComponent(flashMatch[1]);
  document.body.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add("is-visible"));
  setTimeout(() => {
    toast.classList.remove("is-visible");
    setTimeout(() => toast.remove(), 250);
  }, 3200);
})();

// ── No browser autofill inside modals ────────────────────────────────────────
// Chrome's autofill dropdown (previously-typed values) is noise on fields
// like these — every value here is meant to be typed fresh, not recalled.
document.querySelectorAll("[data-modal] input, [data-modal] select, [data-modal] textarea").forEach((field) => {
  if (!field.hasAttribute("autocomplete") && field.type !== "radio" && field.type !== "checkbox") {
    field.setAttribute("autocomplete", "off");
  }
});

// ── Copy-to-clipboard for curl snippets ─────────────────────────────────────
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;

  let text = button.dataset.copyText;
  if (text === undefined) {
    const block = button.closest(".code-block");
    // A note's own textarea (live, possibly unsaved edits) takes priority
    // over .code-body, an older fallback kept for any other code-block
    // that still relies on it.
    const source = block && (block.querySelector("[data-note-content]") || block.querySelector(".code-body"));
    if (!source) return;
    text = "value" in source ? source.value : source.textContent;
  }
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard API needs a secure context; fall back to a hidden textarea.
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

  const label = button.querySelector("[data-copy-label]");
  const original = label.textContent;
  label.textContent = "Copied";
  button.classList.add("copied");
  setTimeout(() => {
    label.textContent = original;
    button.classList.remove("copied");
  }, 1400);
});

// ── Modals ──────────────────────────────────────────────────────────────────
// Triggers keep a real href to the standalone page, so the flow still works
// with JS disabled and when the server re-renders that page on a 422.
// A stack (not just "the one open modal") because a modal can itself hold
// triggers for another one (e.g. the Collections drawer's "New Collection"
// button) — Escape/Tab-trap need to act on whichever opened last, not
// whichever happens to sit first in the DOM.
let modalStack = [];

function openModal(modal, trigger) {
  modal.hidden = false;
  document.body.style.overflow = "hidden";
  modalStack.push({ modal, trigger: trigger || null });
  const field = modal.querySelector("input, select, textarea");
  if (field) field.focus();
}

function closeModal(modal) {
  modal.hidden = true;
  const index = modalStack.findIndex((entry) => entry.modal === modal);
  const trigger = index === -1 ? null : modalStack[index].trigger;
  if (index !== -1) modalStack.splice(index, 1);
  if (!modalStack.length) document.body.style.overflow = "";
  if (trigger) trigger.focus();
}

document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-modal-open]");
  if (trigger) {
    const modal = document.getElementById(trigger.dataset.modalOpen);
    if (modal) {
      event.preventDefault();
      openModal(modal, trigger);
    }
    return;
  }

  const closer = event.target.closest("[data-modal-close]");
  if (closer) {
    const modal = closer.closest("[data-modal]");
    if (modal) closeModal(modal);
    return;
  }

  // Click on the backdrop itself (not the dialog) dismisses.
  if (event.target.matches("[data-modal]")) closeModal(event.target);
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  const top = modalStack[modalStack.length - 1];
  if (top) closeModal(top.modal);
});

// Keep focus inside the topmost open dialog.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const top = modalStack[modalStack.length - 1];
  const modal = top ? top.modal : null;
  if (!modal) return;

  const focusable = modal.querySelectorAll(
    'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])'
  );
  if (!focusable.length) return;
  const first = focusable[0];
  const last = focusable[focusable.length - 1];

  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});

// ── Autosave ────────────────────────────────────────────────────────────────
// Steps created by "+ Add Step" start empty, so anything typed into them was
// lost unless the per-step "Save" button was pressed — an exported document
// then showed blank step text and expected result. Forms marked
// [data-autosave] now persist themselves as you type. The manual submit
// button stays in the markup and is only hidden once this script runs, so the
// page still works without JS.
const SAVE_LABELS = {
  editing: "Unsaved changes",
  saving: "Saving…",
  saved: "Saved",
  error: "Not saved — retry",
};

// The indicator lives beside the form (a step block's header, or the card
// head for Section 1), so resolve it from the nearest enclosing block rather
// than from inside the form. Scoping to .step first keeps sibling steps in
// the same section card from sharing one indicator.
function indicatorFor(form) {
  // .code-block before .card: a note's own block, not the shared Note
  // Section card holding every other note too (same reasoning as .step).
  const scope = form.closest(".step") || form.closest(".code-block") || form.closest(".card") || form;
  return scope.querySelector("[data-save-state]");
}

function setSaveState(form, state) {
  const indicator = indicatorFor(form);
  if (!indicator) return;
  indicator.textContent = SAVE_LABELS[state] || "";
  indicator.dataset.state = state;
}

async function submitAutosave(form) {
  setSaveState(form, "saving");
  try {
    const response = await fetch(form.action, {
      method: "POST",
      body: new FormData(form),
      headers: { "X-Requested-With": "fetch" },
    });
    setSaveState(form, response.ok ? "saved" : "error");
  } catch {
    setSaveState(form, "error");
  }
}

document.querySelectorAll("form[data-autosave]").forEach((form) => {
  form.querySelectorAll("[data-manual-save]").forEach((button) => {
    button.hidden = true;
  });

  let timer;
  form.addEventListener("input", () => {
    clearTimeout(timer);
    setSaveState(form, "editing");
    timer = setTimeout(() => submitAutosave(form), 700);
  });
  // Selects and date pickers commit in one gesture — save immediately.
  form.addEventListener("change", (event) => {
    if (event.target.matches("select, input[type=date]")) {
      clearTimeout(timer);
      submitAutosave(form);
    }
  });
  // Don't lose the last keystrokes if the tab is closed mid-debounce.
  form.addEventListener("focusout", () => {
    if (indicatorFor(form)?.dataset.state === "editing") {
      clearTimeout(timer);
      submitAutosave(form);
    }
  });
});

// ── Keep the scroll position across full-page form posts ────────────────────
// Adding a step or a section posts and redirects, which used to drop the
// viewport back at the top of a long execution page. Stash the offset on
// submit and put it back after the reload.
const SCROLL_KEY = `qa-toolbox:scroll:${location.pathname}`;

if ("scrollRestoration" in history) {
  history.scrollRestoration = "manual";
}

document.addEventListener("submit", (event) => {
  // Autosave posts via fetch and never reloads, so it needs no stashing.
  if (event.target.matches("form[data-autosave]")) return;
  try {
    sessionStorage.setItem(SCROLL_KEY, String(window.scrollY));
  } catch {
    /* private mode or storage disabled — scroll just won't be restored */
  }
});

(function restoreScroll() {
  let saved = null;
  try {
    saved = sessionStorage.getItem(SCROLL_KEY);
    if (saved !== null) sessionStorage.removeItem(SCROLL_KEY);
  } catch {
    return;
  }
  if (saved === null) return;

  const target = parseInt(saved, 10);
  if (Number.isNaN(target)) return;

  // Run once now and once after load: images and fonts settling can change
  // the document height between the two.
  const apply = () => window.scrollTo(0, target);
  requestAnimationFrame(apply);
  window.addEventListener("load", () => requestAnimationFrame(apply), { once: true });
})();

// ── Drag to reorder (sections and steps) ────────────────────────────────────
// Shared by the test case execution page and the prebuilt template editor.
// Sections reorder across a whole [data-sections] list; steps reorder within
// their own section's [data-steps] list, so drags never cross section
// boundaries.
document.querySelectorAll("[data-sections]").forEach((el) =>
  initReorder(el, { itemSelector: ".section-card", idKey: "sectionId", indexSelector: "[data-section-index]" })
);
document.querySelectorAll("[data-steps]").forEach((el) =>
  initReorder(el, { itemSelector: ".step", idKey: "stepId", indexSelector: "[data-step-index]" })
);

function initReorder(container, { itemSelector, idKey, indexSelector }) {
  const items = () => Array.from(container.querySelectorAll(itemSelector));
  // A test case page has a Description card above the section list, so its
  // section numbering starts at 2; everywhere else (steps, prebuilt
  // sections) starts at 1. data-index-offset lets each container say which.
  const indexOffset = parseInt(container.dataset.indexOffset || "1", 10);
  let dragging = null;

  function setState(item, text, state) {
    container.querySelectorAll("[data-reorder-state]").forEach((el) => {
      el.textContent = "";
      delete el.dataset.state;
    });
    const indicator = item && item.querySelector("[data-reorder-state]");
    if (indicator) {
      indicator.textContent = text;
      indicator.dataset.state = state;
    }
  }

  function renumber() {
    items().forEach((item, index) => {
      const label = item.querySelector(indexSelector);
      if (label) label.textContent = String(index + indexOffset);
    });
  }

  // `item` is passed in because dragend clears `dragging` synchronously,
  // before this promise resolves — reading it after the await would leave the
  // confirmation with nowhere to render.
  async function persist(item) {
    const order = items().map((el) => el.dataset[idKey]).join(",");
    const body = new FormData();
    body.append("order", order);
    setState(item, "Saving…", "saving");
    try {
      const response = await fetch(container.dataset.reorderAction, { method: "POST", body });
      setState(item, response.ok ? "Order saved" : "Not saved", response.ok ? "saved" : "error");
    } catch {
      setState(item, "Not saved", "error");
    }
    setTimeout(() => setState(item, "", ""), 1600);
  }

  // A handle-only drag would use the handle as the drag image. Flipping the
  // item's draggable flag on handle press makes the whole item the subject
  // while still leaving text in it selectable the rest of the time.
  container.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest("[data-drag-handle]");
    if (!handle) return;
    const item = handle.closest(itemSelector);
    if (item) item.draggable = true;
  });

  document.addEventListener("pointerup", () => {
    items().forEach((item) => {
      item.draggable = false;
    });
  });

  container.addEventListener("dragstart", (event) => {
    const item = event.target.closest(itemSelector);
    if (!item || !item.draggable) return;
    dragging = item;
    item.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    // Firefox needs data set for a drag to start at all.
    event.dataTransfer.setData("text/plain", item.dataset[idKey]);
  });

  container.addEventListener("dragover", (event) => {
    if (!dragging) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";

    const after = items().find((item) => {
      if (item === dragging) return false;
      const box = item.getBoundingClientRect();
      return event.clientY < box.top + box.height / 2;
    });

    if (after) {
      if (after !== dragging.nextElementSibling) container.insertBefore(dragging, after);
    } else if (container.lastElementChild !== dragging) {
      container.appendChild(dragging);
    }
  });

  container.addEventListener("drop", (event) => {
    if (dragging) event.preventDefault();
  });

  container.addEventListener("dragend", () => {
    if (!dragging) return;
    const moved = dragging;
    dragging = null;
    moved.classList.remove("is-dragging");
    moved.draggable = false;
    renumber();
    persist(moved);
  });
}

// ── Assignee mirrors Tester until manually touched ──────────────────────────
// On page load, an Assignee that already has a value (editing an existing
// record) counts as already "touched" — Tester changes must never silently
// overwrite a deliberately-set Assignee. A blank Assignee (a fresh create
// form) starts untouched, so it mirrors Tester until the user picks
// something themselves. Both selects use the "change" event (not "input" —
// a <select> doesn't fire that consistently across browsers the way a text
// field does).
document.querySelectorAll('select[name="assignee_id"]').forEach((select) => {
  if (select.value) select.dataset.touched = "1";
});

// Registered on the capture phase (not the default bubble phase) so this
// runs BEFORE any bubble-phase "change" listener on a nearer ancestor —
// notably testcases/execute.html's per-form autosave listener, which reads
// the form's current field values via FormData as soon as the event reaches
// the <form>. On the bubble phase this listener (bound to `document`, the
// farthest ancestor) would fire last, after autosave already captured the
// stale Assignee value — and since setting `.value` via JS never fires its
// own "change" event, autosave would never re-run to pick up the mirrored
// value. Capture-phase listeners on an ancestor always run before
// bubble-phase listeners on a descendant for the same event, so mirroring
// Assignee here guarantees the form's own change handlers (autosave
// included) see the updated value.
document.addEventListener(
  "change",
  (event) => {
    if (event.target.matches('select[name="assignee_id"]')) {
      event.target.dataset.touched = "1";
      return;
    }
    if (event.target.matches('select[name="tester_id"]')) {
      const form = event.target.closest("form");
      const assignee = form?.querySelector('select[name="assignee_id"]');
      if (assignee && !assignee.dataset.touched) assignee.value = event.target.value;
    }
  },
  true
);

// ── Prebuilt picker: search/filter, pagination, and title autofill ──────────
// "Blank" is pinned — always visible, never paginated or filtered away.
// Everything else is filtered by search/service/test-type, then sliced into
// pages of PREBUILT_PAGE_SIZE so a large template library stays scannable.
const PREBUILT_PAGE_SIZE = 6;

function prebuiltRealOptions(field) {
  return Array.from(field.querySelectorAll("[data-prebuilt-option]")).filter((o) => o.dataset.name !== "");
}

function applyPrebuiltView(field, resetPage) {
  if (!field) return;
  const search = (field.querySelector("[data-prebuilt-search]")?.value || "").trim().toLowerCase();
  const filters = {};
  field.querySelectorAll("[data-prebuilt-filter]").forEach((select) => {
    if (select.value) filters[select.dataset.prebuiltFilter] = select.value;
  });

  const matches = prebuiltRealOptions(field).filter((option) => {
    const matchesSearch = !search || option.dataset.name.includes(search);
    const matchesFilters = Object.entries(filters).every(([key, value]) => option.dataset[key] === value);
    return matchesSearch && matchesFilters;
  });

  if (resetPage) field.dataset.prebuiltPage = "0";
  const totalPages = Math.max(1, Math.ceil(matches.length / PREBUILT_PAGE_SIZE));
  let page = parseInt(field.dataset.prebuiltPage || "0", 10);
  page = Math.min(Math.max(page, 0), totalPages - 1);
  field.dataset.prebuiltPage = String(page);

  const start = page * PREBUILT_PAGE_SIZE;
  const visible = new Set(matches.slice(start, start + PREBUILT_PAGE_SIZE));
  prebuiltRealOptions(field).forEach((option) => {
    option.hidden = !visible.has(option);
  });

  const empty = field.querySelector("[data-prebuilt-empty]");
  if (empty) empty.hidden = matches.length > 0;

  const pager = field.querySelector("[data-prebuilt-pager]");
  if (pager) {
    pager.hidden = totalPages <= 1;
    const label = pager.querySelector("[data-prebuilt-page-label]");
    if (label) label.textContent = `Page ${page + 1} of ${totalPages}`;
    const prev = pager.querySelector("[data-prebuilt-prev]");
    const next = pager.querySelector("[data-prebuilt-next]");
    if (prev) prev.disabled = page === 0;
    if (next) next.disabled = page >= totalPages - 1;
  }
}

// Paginate every picker on load, even before any search/filter interaction.
document.querySelectorAll("[data-prebuilt-list]").forEach((list) => applyPrebuiltView(list.closest(".field"), true));

document.addEventListener("input", (event) => {
  if (event.target.matches("[data-prebuilt-search]")) applyPrebuiltView(event.target.closest(".field"), true);
});

document.addEventListener("change", (event) => {
  if (event.target.matches("[data-prebuilt-filter]")) applyPrebuiltView(event.target.closest(".field"), true);

  if (event.target.matches('input[name="prebuilt_id"]')) {
    const form = event.target.closest("form");
    const name = event.target.dataset.prebuiltName;
    const title = form?.querySelector('input[name="title"]');
    if (title) title.value = name || ""; // Blank clears it back out, a real template fills it in

    const previewTarget = form?.querySelector("[data-prebuilt-preview-target]");
    if (previewTarget) {
      if (!event.target.value) {
        previewTarget.innerHTML =
          '<div class="muted">Blank template &mdash; Pre Condition, Main Test and Post Condition with no steps.</div>';
      } else {
        const tpl = document.querySelector(`template[data-prebuilt-preview="${event.target.value}"]`);
        previewTarget.innerHTML = tpl ? tpl.innerHTML : "";
      }
    }
  }
});

document.addEventListener("click", (event) => {
  const prev = event.target.closest("[data-prebuilt-prev]");
  if (prev) {
    const field = prev.closest(".field");
    field.dataset.prebuiltPage = String(Math.max(0, parseInt(field.dataset.prebuiltPage || "0", 10) - 1));
    applyPrebuiltView(field, false);
    return;
  }
  const next = event.target.closest("[data-prebuilt-next]");
  if (next) {
    const field = next.closest(".field");
    field.dataset.prebuiltPage = String(parseInt(field.dataset.prebuiltPage || "0", 10) + 1);
    applyPrebuiltView(field, false);
  }
});

// ── Collapsible sidebar ─────────────────────────────────────────────────────
// The choice is applied before paint by an inline script in <head>, so the
// rail never flashes open on navigation; this only handles the toggle.
(function initSidebarToggle() {
  const KEY = "qa-toolbox:sidebar-collapsed";
  const toggle = document.querySelector("[data-sidebar-toggle]");
  if (!toggle) return;

  function sync() {
    const collapsed = document.body.classList.contains("is-collapsed");
    const text = collapsed ? "Expand sidebar" : "Collapse sidebar";
    toggle.title = text;
    toggle.setAttribute("aria-label", text);
    toggle.setAttribute("aria-expanded", String(!collapsed));
  }

  toggle.addEventListener("click", () => {
    const collapsed = document.body.classList.toggle("is-collapsed");
    try {
      localStorage.setItem(KEY, collapsed ? "1" : "0");
    } catch {
      /* storage unavailable — the choice just won't persist */
    }
    sync();
  });

  sync();
})();

// ── Light/dark theme ─────────────────────────────────────────────────────
// The choice is applied before paint by an inline script in <head>, so the
// page never flashes light-then-dark; this only handles the toggle.
(function initThemeToggle() {
  const KEY = "qa-toolbox:theme";
  const toggle = document.querySelector("[data-theme-toggle]");
  if (!toggle) return;
  const label = toggle.querySelector("[data-theme-label]");

  function sync() {
    const dark = document.documentElement.getAttribute("data-theme") === "dark";
    const text = dark ? "Switch to light theme" : "Switch to dark theme";
    toggle.title = text;
    toggle.setAttribute("aria-label", text);
    if (label) label.textContent = dark ? "Light theme" : "Dark theme";
  }

  toggle.addEventListener("click", () => {
    const dark = document.documentElement.getAttribute("data-theme") !== "dark";
    if (dark) {
      document.documentElement.setAttribute("data-theme", "dark");
    } else {
      document.documentElement.removeAttribute("data-theme");
    }
    try {
      localStorage.setItem(KEY, dark ? "dark" : "light");
    } catch {
      /* storage unavailable — the choice just won't persist */
    }
    sync();
  });

  sync();
})();

// ── Note Section: guess the snippet's language from what got pasted ─────────
function detectSnippetLanguage(text) {
  const trimmed = text.trim();
  if (!trimmed) return null;

  if (/^curl\b/i.test(trimmed)) return "CURL";

  try {
    JSON.parse(trimmed);
    return "JSON";
  } catch {
    /* not JSON — keep checking */
  }

  if (/^(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+(TABLE|INDEX|VIEW)|ALTER\s+TABLE|DROP\s+TABLE|WITH)\b/i.test(trimmed)) {
    return "SQL";
  }

  if (/^<\?xml/i.test(trimmed) || (/^<[a-zA-Z!][^>]*>/.test(trimmed) && /<\/[a-zA-Z][^>]*>\s*$/.test(trimmed))) {
    return "XML";
  }

  if (/^#!.*\b(bash|sh)\b/.test(trimmed) || /^\s*(if|for|while)\s*\[.*\]\s*;\s*then\b/m.test(trimmed) || /^\$\s+\S/m.test(trimmed)) {
    return "BASH";
  }

  if (/^\s*(import\s+\w|from\s+\w+\s+import|def\s+\w+\s*\(|print\()/m.test(trimmed)) {
    return "PYTHON";
  }

  if (/\b(function\s*\w*\s*\(|=>|const\s+\w+\s*=|let\s+\w+\s*=|console\.log\()/.test(trimmed)) {
    return "JAVASCRIPT";
  }

  if (/^---/.test(trimmed) || /^[\w.-]+:\s?.+$/m.test(trimmed)) {
    return "YAML";
  }

  return "TEXT";
}

// Detected at submit time, against whatever the field actually holds, rather
// than at paste time against just the pasted text: the language field is
// hidden (no dropdown to show a live guess to), so there's no reason to
// commit to a guess before the user is done — typing after a paste, editing
// a paste, or pasting more than once should all still land on the type that
// matches what's actually being saved.
document.addEventListener("submit", (event) => {
  const contentField = event.target.querySelector("[data-note-content]");
  const languageField = event.target.querySelector("[data-note-language]");
  if (!contentField || !languageField) return;
  languageField.value = detectSnippetLanguage(contentField.value) || "TEXT";
});

// Our language names -> the names highlight.js registers them under (see
// app/static/js/vendor/highlightjs/README.md for the vendored bundle).
const HLJS_LANGUAGE_MAP = {
  CURL: "bash", JSON: "json", SQL: "sql", TEXT: "plaintext",
  YAML: "yaml", XML: "xml", BASH: "bash", PYTHON: "python", JAVASCRIPT: "javascript",
};

// ── Note Section: direct editing ─────────────────────────────────────────
// An existing note's content is now a plain <textarea> inside .snippet-code
// (autosaved via the generic form[data-autosave] handling above) instead of
// a read-only <pre><code> — as opposed to the "+ Add Note" form's own plain
// [data-note-content] textarea below, which stays exactly as it was (fixed
// rows, no gutter). Two things the old static markup got for free need to
// be kept in sync here for the editable one: the line-number gutter, and
// the field's own height (a <textarea> doesn't grow to fit its content the
// way a block of text does).
function syncNoteTextarea(textarea) {
  const scroller = textarea.closest(".snippet-code");
  if (!scroller) return; // the "+ Add Note" textarea — leave it alone
  const gutter = scroller.querySelector(".snippet-gutter");
  if (gutter) {
    const lineCount = textarea.value.split("\n").length;
    let html = "";
    for (let i = 1; i <= lineCount; i++) html += `<span>${i}</span>`;
    gutter.innerHTML = html;
  }
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

document.querySelectorAll("[data-note-content]").forEach(syncNoteTextarea);

// Detected on every keystroke here (autosave never fires a real "submit"
// event, so the submit-time detector above never runs for it) — keeps the
// hidden language field current for whatever the debounced save actually
// sends. Harmless no-op duplication for the "+ Add Note" form, which the
// submit-time detector already covers.
document.addEventListener("input", (event) => {
  if (!event.target.matches("[data-note-content]")) return;
  syncNoteTextarea(event.target);
  const languageField = event.target.closest("form")?.querySelector("[data-note-language]");
  if (languageField) languageField.value = detectSnippetLanguage(event.target.value) || "TEXT";
});

// The delete <form> has to live outside the note's own form (forms can't
// nest — the note's whole block is already one, for autosave) — see
// notes/_panel.html.
document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-note-delete]");
  if (!button) return;
  button.closest(".code-block")?.nextElementSibling?.requestSubmit();
});

// A tiny, deliberately-scoped Markdown subset — headings, bold/italic,
// inline/fenced code, lists, links — rendered for the preview toggle only.
// The source is HTML-escaped FIRST and every tag below is one this function
// adds itself, so there's no way embedded HTML in a note can ever survive
// into the rendered output (the panel's own promise: "stored verbatim,
// nothing is executed").
function escapeHtmlForMarkdown(text) {
  const el = document.createElement("div");
  el.textContent = text;
  return el.innerHTML;
}

function renderNoteMarkdown(rawText) {
  const inline = (s) => s
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/\*([^*]+)\*/g, "<em>$1</em>")
    .replace(/\[([^\]]+)\]\(((?:https?:|mailto:)[^\s)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

  const html = [];
  let list = null; // { tag: "ul"|"ol", items: [] }
  let inFence = false;
  let fenceLines = [];

  function closeList() {
    if (!list) return;
    html.push(`<${list.tag}>${list.items.map((item) => `<li>${inline(item)}</li>`).join("")}</${list.tag}>`);
    list = null;
  }

  escapeHtmlForMarkdown(rawText).split("\n").forEach((line) => {
    if (/^```/.test(line.trim())) {
      if (inFence) {
        html.push(`<pre><code>${fenceLines.join("\n")}</code></pre>`);
        fenceLines = [];
      } else {
        closeList();
      }
      inFence = !inFence;
      return;
    }
    if (inFence) {
      fenceLines.push(line);
      return;
    }
    const heading = line.match(/^(#{1,6})\s+(.*)$/);
    if (heading) {
      closeList();
      html.push(`<h${heading[1].length}>${inline(heading[2])}</h${heading[1].length}>`);
      return;
    }
    const ordered = line.match(/^\d+\.\s+(.*)$/);
    const unordered = line.match(/^[-*]\s+(.*)$/);
    if (ordered || unordered) {
      const tag = ordered ? "ol" : "ul";
      if (!list || list.tag !== tag) { closeList(); list = { tag, items: [] }; }
      list.items.push((ordered || unordered)[1]);
      return;
    }
    closeList();
    if (line.trim()) html.push(`<p>${inline(line)}</p>`);
  });
  closeList();
  if (inFence && fenceLines.length) html.push(`<pre><code>${fenceLines.join("\n")}</code></pre>`);
  return html.join("\n");
}

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-note-preview-toggle]");
  if (!button) return;
  const block = button.closest(".code-block");
  const rawView = block.querySelector("[data-note-raw-view]");
  const previewView = block.querySelector("[data-note-preview-view]");
  const textarea = block.querySelector("[data-note-content]");
  const showingPreview = !previewView.hidden;
  if (showingPreview) {
    previewView.hidden = true;
    rawView.hidden = false;
  } else {
    previewView.innerHTML = renderNoteMarkdown(textarea.value);
    previewView.hidden = false;
    rawView.hidden = true;
  }
  button.classList.toggle("is-active", !showingPreview);
});

// A header checkbox with data-select-all="<css selector>" toggles every
// checkbox matching that selector (used by the test case export/import
// checklists — see subtasks/detail.html and testcases/import_preview.html).
document.addEventListener("change", (event) => {
  const selectAll = event.target.closest("[data-select-all]");
  if (selectAll) {
    document.querySelectorAll(selectAll.dataset.selectAll).forEach((cb) => {
      cb.checked = selectAll.checked;
    });
  }
});

// A button with data-submit-selected="<hidden form id>" copies every checked
// checkbox in data-selection-name="<name>" into that form as hidden inputs,
// then submits it. Keeps the bulk-export form separate from the per-row
// delete <form>s in the same table (forms can't nest).
document.addEventListener("click", (event) => {
  const trigger = event.target.closest("[data-submit-selected]");
  if (!trigger) return;
  const form = document.getElementById(trigger.dataset.submitSelected);
  if (!form) return;
  const checked = document.querySelectorAll(`[data-selection-name="${trigger.dataset.selectionName}"]:checked`);
  if (checked.length === 0) return;
  form.querySelectorAll('input[data-generated="1"]').forEach((el) => el.remove());
  checked.forEach((cb) => {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = trigger.dataset.selectionName;
    input.value = cb.value;
    input.dataset.generated = "1";
    form.appendChild(input);
  });
  form.submit();
});

document.querySelectorAll("[data-snippet-code]").forEach((block) => {
  if (!window.hljs) return; // vendored bundle failed to load — plain text is still readable
  const lang = HLJS_LANGUAGE_MAP[block.dataset.snippetCode] || "plaintext";
  block.classList.add(`language-${lang}`);
  window.hljs.highlightElement(block);
});
