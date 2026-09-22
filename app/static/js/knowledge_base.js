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

  async function handleFiles(files) {
    for (const file of files) {
      try {
        const { url, is_image } = await uploadCardFile(cardId, file);
        insertAtCursor(textarea, is_image ? `![${file.name}](${url})` : `[${file.name}](${url})`);
      } catch {
        // Upload failed — leave the textarea as-is rather than insert a
        // broken reference; the user can retry the paste/drop.
      }
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
