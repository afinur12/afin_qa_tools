// ── Copy-to-clipboard for curl snippets ─────────────────────────────────────
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;

  const block = button.closest(".code-block");
  const body = block && block.querySelector(".code-body");
  if (!body) return;

  const text = body.textContent;
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
let lastTrigger = null;

function openModal(modal, trigger) {
  lastTrigger = trigger || null;
  modal.hidden = false;
  document.body.style.overflow = "hidden";
  const field = modal.querySelector("input, select, textarea");
  if (field) field.focus();
}

function closeModal(modal) {
  modal.hidden = true;
  document.body.style.overflow = "";
  if (lastTrigger) {
    lastTrigger.focus();
    lastTrigger = null;
  }
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
  const open = document.querySelector("[data-modal]:not([hidden])");
  if (open) closeModal(open);
});

// Keep focus inside an open dialog.
document.addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const modal = document.querySelector("[data-modal]:not([hidden])");
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
  const scope = form.closest(".step") || form.closest(".card") || form;
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

// ── Drag to reorder sections ────────────────────────────────────────────────
(function initSectionReorder() {
  const container = document.querySelector("[data-sections]");
  if (!container) return;

  const cards = () => Array.from(container.querySelectorAll(".section-card"));
  let dragging = null;

  function setState(card, text, state) {
    container.querySelectorAll("[data-reorder-state]").forEach((el) => {
      el.textContent = "";
      delete el.dataset.state;
    });
    const indicator = card && card.querySelector("[data-reorder-state]");
    if (indicator) {
      indicator.textContent = text;
      indicator.dataset.state = state;
    }
  }

  function renumber() {
    cards().forEach((card, index) => {
      const label = card.querySelector("[data-section-index]");
      // Card 1 is the Description panel, so sections start at 2.
      if (label) label.textContent = String(index + 2);
    });
  }

  // `card` is passed in because dragend clears `dragging` synchronously,
  // before this promise resolves — reading it after the await would leave the
  // confirmation with nowhere to render.
  async function persist(card) {
    const order = cards().map((item) => item.dataset.sectionId).join(",");
    const body = new FormData();
    body.append("order", order);
    setState(card, "Saving…", "saving");
    try {
      const response = await fetch(container.dataset.reorderAction, { method: "POST", body });
      setState(card, response.ok ? "Order saved" : "Not saved", response.ok ? "saved" : "error");
    } catch {
      setState(card, "Not saved", "error");
    }
    setTimeout(() => setState(card, "", ""), 1600);
  }

  // A handle-only drag would use the handle as the drag image. Flipping the
  // card's draggable flag on handle press makes the whole card the subject
  // while still leaving text in the card selectable the rest of the time.
  container.addEventListener("pointerdown", (event) => {
    const handle = event.target.closest("[data-drag-handle]");
    if (!handle) return;
    const card = handle.closest(".section-card");
    if (card) card.draggable = true;
  });

  document.addEventListener("pointerup", () => {
    cards().forEach((card) => {
      card.draggable = false;
    });
  });

  container.addEventListener("dragstart", (event) => {
    const card = event.target.closest(".section-card");
    if (!card || !card.draggable) return;
    dragging = card;
    card.classList.add("is-dragging");
    event.dataTransfer.effectAllowed = "move";
    // Firefox needs data set for a drag to start at all.
    event.dataTransfer.setData("text/plain", card.dataset.sectionId);
  });

  container.addEventListener("dragover", (event) => {
    if (!dragging) return;
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";

    const after = cards().find((card) => {
      if (card === dragging) return false;
      const box = card.getBoundingClientRect();
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
})();

// ── Prebuilt picker: search/filter and title autofill ───────────────────────
function filterPrebuiltOptions(control) {
  const field = control.closest(".field");
  if (!field) return;
  const search = (field.querySelector("[data-prebuilt-search]")?.value || "").trim().toLowerCase();
  const filters = {};
  field.querySelectorAll("[data-prebuilt-filter]").forEach((select) => {
    if (select.value) filters[select.dataset.prebuiltFilter] = select.value;
  });

  let anyVisible = false;
  field.querySelectorAll("[data-prebuilt-option]").forEach((option) => {
    const isBlank = option.dataset.name === "";
    const matchesSearch = isBlank || !search || option.dataset.name.includes(search);
    const matchesFilters = isBlank || Object.entries(filters).every(([key, value]) => option.dataset[key] === value);
    const visible = matchesSearch && matchesFilters;
    option.hidden = !visible;
    if (visible) anyVisible = true;
  });

  const empty = field.querySelector("[data-prebuilt-empty]");
  if (empty) empty.hidden = anyVisible;
}

document.addEventListener("input", (event) => {
  if (event.target.matches("[data-prebuilt-search]")) filterPrebuiltOptions(event.target);
});

document.addEventListener("change", (event) => {
  if (event.target.matches("[data-prebuilt-filter]")) filterPrebuiltOptions(event.target);

  if (event.target.matches('input[name="prebuilt_id"]')) {
    const name = event.target.dataset.prebuiltName;
    if (!name) return; // "Blank" carries no name — leave whatever the user typed
    const title = event.target.closest("form")?.querySelector('input[name="title"]');
    if (title) title.value = name;
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
