// Knowledge Base card editor: preview toggle (reusing the shared
// renderNoteMarkdown from app.js) and paste/drop-to-upload for images and
// files, inserting a markdown reference at the cursor. Autosave itself is
// NOT implemented here — the editor's <form data-autosave> is picked up by
// the generic handler already wired up app-wide in app.js.

document.addEventListener("click", (event) => {
  const button = event.target.closest("[data-card-preview-toggle]");
  if (!button) return;
  const card = button.closest(".card");
  const rawView = card.querySelector("[data-card-raw-view]");
  const previewView = card.querySelector("[data-card-preview-view]");
  const textarea = card.querySelector("[data-card-content]");
  const showingPreview = !previewView.hidden;
  if (showingPreview) {
    previewView.hidden = true;
    rawView.hidden = false;
  } else {
    previewView.innerHTML = renderNoteMarkdown(textarea.value);
    previewView.querySelectorAll("pre code[class^='language-']").forEach((block) => {
      if (window.hljs) window.hljs.highlightElement(block);
    });
    previewView.hidden = false;
    rawView.hidden = true;
  }
  button.classList.toggle("is-active", !showingPreview);
});

function insertAtCursor(textarea, text) {
  const start = textarea.selectionStart;
  const end = textarea.selectionEnd;
  textarea.setRangeText(text, start, end, "end");
  textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

async function uploadCardFile(cardId, file) {
  const formData = new FormData();
  formData.append("file", file);
  const response = await fetch(`/knowledge-base/${cardId}/upload`, {
    method: "POST",
    body: formData,
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error(String(response.status));
  return response.json();
}

document.querySelectorAll("[data-card-content]").forEach((textarea) => {
  const cardId = window.location.pathname.split("/").pop();
  // The same [data-save-state] span the generic autosave mechanism in
  // app.js drives (see indicatorFor()/setSaveState() there) — reused here
  // for transient upload status so a failed/in-flight upload isn't silent.
  const saveState = textarea.closest(".card")?.querySelector("[data-save-state]");

  async function handleFiles(files) {
    if (saveState) saveState.textContent = "Uploading…";
    let failed = 0;
    for (const file of files) {
      try {
        const { url, is_image } = await uploadCardFile(cardId, file);
        // Square brackets/parens in the file name would otherwise break the
        // markdown link/image syntax itself; the display text is still run
        // through escapeHtmlForMarkdown on render, so this is only about
        // keeping the markdown well-formed, not escaping HTML.
        const safeName = file.name.replace(/[[\]()]/g, "_");
        insertAtCursor(textarea, is_image ? `![${safeName}](${url})` : `[${safeName}](${url})`);
        // insertAtCursor's synthetic "input" event drives the normal
        // autosave indicator (editing -> saving -> saved) from here, so
        // "Uploading…" naturally gets replaced without any extra code.
      } catch {
        // Upload failed — leave the textarea as-is rather than insert a
        // broken reference; the user can retry the paste/drop. Surface the
        // failure instead of swallowing it silently.
        failed += 1;
      }
    }
    if (failed && saveState) {
      saveState.textContent = `${failed} image(s) failed to upload`;
      saveState.dataset.state = "error";
      setTimeout(() => {
        if (saveState.dataset.state === "error") {
          saveState.textContent = "";
          delete saveState.dataset.state;
        }
      }, 3200);
    }
  }

  textarea.addEventListener("paste", (event) => {
    const items = event.clipboardData ? Array.from(event.clipboardData.items) : [];
    const files = items.map((item) => item.getAsFile()).filter(Boolean);
    if (!files.length) return;
    event.preventDefault();
    handleFiles(files);
  });

  textarea.addEventListener("dragover", (event) => event.preventDefault());
  textarea.addEventListener("drop", (event) => {
    if (!event.dataTransfer || !event.dataTransfer.files.length) return;
    event.preventDefault();
    handleFiles(Array.from(event.dataTransfer.files));
  });
});
