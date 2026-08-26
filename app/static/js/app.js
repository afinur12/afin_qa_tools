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
