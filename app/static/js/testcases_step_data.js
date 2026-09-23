// Test Case execute page: Test Data items (see the data_item_block macro in
// app/templates/testcases/execute.html). A value shows as a plain editable
// textarea while focused, and swaps to a read-only, syntax-highlighted
// <pre><code> once you click/tab away — highlight.js can't meaningfully
// color a live <textarea>, only a static <code> element, so this is the
// closest thing to "always looks highlighted" that doesn't require a
// pixel-synced textarea/overlay editor.
//
// The initial highlight on page load (for an item that already has a saved
// value) is handled for free by app.js's existing [data-snippet-code] loop
// — this file only needs to handle RE-highlighting after an edit, since
// that loop only ever runs once, at load.

function reHighlightStepDataCode(codeEl) {
  if (!window.hljs) return;
  // hljs.highlightElement isn't safely re-callable on an already-highlighted
  // node without clearing its own bookkeeping first.
  codeEl.className = codeEl.className.replace(/\blanguage-\S+/g, "").replace(/\bhljs\b/g, "").trim();
  delete codeEl.dataset.highlighted;
  const lang = HLJS_LANGUAGE_MAP[codeEl.dataset.snippetCode] || "plaintext";
  codeEl.classList.add(`language-${lang}`);
  window.hljs.highlightElement(codeEl);
}

document.querySelectorAll("[data-step-data-textarea]").forEach((textarea) => {
  const wrap = textarea.closest("[data-step-data-code-wrap]");
  const highlightedView = wrap.querySelector("[data-step-data-highlighted-view]");
  const codeEl = wrap.querySelector("[data-step-data-highlighted-code]");
  const form = textarea.closest("form");
  const languageField = form.querySelector("[data-note-language]");
  const languageLabel = form.querySelector("[data-step-data-lang-label]");

  function showEditable() {
    highlightedView.hidden = true;
    textarea.hidden = false;
    textarea.focus();
  }

  function showHighlighted() {
    const text = textarea.value;
    if (!text.trim()) {
      // Nothing to highlight yet — stay in edit mode so an empty new item
      // doesn't collapse into a blank, unclickable box.
      textarea.hidden = false;
      highlightedView.hidden = true;
      return;
    }
    const lang = detectSnippetLanguage(text) || "TEXT";
    languageField.value = lang;
    if (languageLabel) languageLabel.textContent = lang;
    codeEl.textContent = text;
    codeEl.dataset.snippetCode = lang;
    reHighlightStepDataCode(codeEl);
    textarea.hidden = true;
    highlightedView.hidden = false;
  }

  highlightedView.addEventListener("click", showEditable);
  highlightedView.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      showEditable();
    }
  });
  textarea.addEventListener("blur", showHighlighted);
});
