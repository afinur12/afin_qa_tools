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

// ── Beautify / format ───────────────────────────────────────────────────
// Only languages with an unambiguous, deterministic "pretty" form get a real
// formatter: JSON (built in), SQL (vendored sql-formatter, same one the
// standalone SQL Formatter utility uses), cURL (a from-scratch multi-line
// reflow, since no vendored curl formatter exists — including pretty-printing
// any JSON body handed to -d/--data), and XML (a naive but standard
// indent-by-tag-depth pass). Anything else (TEXT, YAML, BASH, PYTHON,
// JAVASCRIPT, and formats this feature doesn't detect at all, like Markdown)
// has no formatter here and the button is a no-op with visible feedback
// rather than silently doing nothing.

function tokenizeCurlLike(text) {
  const tokens = [];
  const re = /'[^']*'|"[^"]*"|\S+/g;
  let match;
  while ((match = re.exec(text))) tokens.push(match[0]);
  return tokens;
}

function prettyJsonToken(token, indent) {
  const quoteChar = token[0];
  if (quoteChar !== "'" && quoteChar !== '"') return token;
  const inner = token.slice(1, -1);
  try {
    const parsed = JSON.parse(inner);
    const pretty = JSON.stringify(parsed, null, 2).split("\n").join("\n" + indent);
    return quoteChar + pretty + quoteChar;
  } catch {
    return token;
  }
}

function formatCurlValue(text) {
  // Deliberately simple: splits on whitespace outside of quotes, so a flag
  // value with an escaped quote inside it won't round-trip perfectly. Good
  // enough for the curl commands QA engineers paste in by hand.
  const tokens = tokenizeCurlLike(text);
  if (tokens.length === 0 || tokens[0].toLowerCase() !== "curl") return null;
  const indent = "  ";
  const lines = [];
  let current = ["curl"];
  let i = 1;
  if (tokens[i] && !tokens[i].startsWith("-")) {
    current.push(tokens[i]);
    i += 1;
  }
  lines.push(current.join(" "));
  while (i < tokens.length) {
    const tok = tokens[i];
    if (tok.startsWith("-")) {
      let line = tok;
      if (tokens[i + 1] && !tokens[i + 1].startsWith("-")) {
        line += " " + prettyJsonToken(tokens[i + 1], indent);
        i += 2;
      } else {
        i += 1;
      }
      lines.push(line);
    } else {
      lines.push(tok);
      i += 1;
    }
  }
  if (lines.length === 1) return null;
  return lines.join(" \\\n" + indent);
}

function formatXmlValue(text) {
  const trimmed = text.trim();
  if (!trimmed.startsWith("<")) return null;
  const withBreaks = trimmed.replace(/>\s*</g, ">\n<");
  const lines = withBreaks.split("\n");
  let depth = 0;
  const out = [];
  for (const line of lines) {
    const isClosing = /^<\//.test(line);
    const isSelfClosing = /\/>\s*$/.test(line) || /^<\?/.test(line) || /^<!--/.test(line);
    const isOpeningOnly = /^<[^/!?][^>]*[^/]>$/.test(line);
    if (isClosing) depth = Math.max(0, depth - 1);
    out.push("  ".repeat(depth) + line);
    if (!isClosing && !isSelfClosing && isOpeningOnly) depth += 1;
  }
  return out.join("\n");
}

function formatSqlValue(text) {
  if (!window.sqlFormatter) return null;
  return window.sqlFormatter.format(text, { language: "sql", keywordCase: "upper", tabWidth: 2 });
}

function formatStepDataValue(text, language) {
  const trimmed = text.trim();
  if (!trimmed) return null;
  try {
    if (language === "JSON") return JSON.stringify(JSON.parse(trimmed), null, 2);
    if (language === "SQL") return formatSqlValue(trimmed);
    if (language === "CURL") return formatCurlValue(trimmed);
    if (language === "XML") return formatXmlValue(trimmed);
  } catch {
    return null;
  }
  return null;
}

function flashFormatError(el) {
  el.classList.add("is-error");
  setTimeout(() => el.classList.remove("is-error"), 700);
}

document.querySelectorAll("[data-step-data-textarea]").forEach((textarea) => {
  const wrap = textarea.closest("[data-step-data-code-wrap]");
  const highlightedView = wrap.querySelector("[data-step-data-highlighted-view]");
  const codeEl = wrap.querySelector("[data-step-data-highlighted-code]");
  const form = textarea.closest("form");
  const languageField = form.querySelector("[data-note-language]");
  const languageLabel = form.querySelector("[data-step-data-lang-label]");
  const toggleBtn = form.querySelector("[data-step-data-toggle]");
  const formatBtn = form.querySelector("[data-step-data-format]");

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

  function expand() {
    form.classList.remove("is-collapsed");
    wrap.hidden = false;
    if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
  }

  highlightedView.addEventListener("click", showEditable);
  highlightedView.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      showEditable();
    }
  });
  textarea.addEventListener("blur", showHighlighted);

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const collapsed = form.classList.toggle("is-collapsed");
      wrap.hidden = collapsed;
      toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
    });
  }

  if (formatBtn) {
    formatBtn.addEventListener("click", () => {
      const language = (languageField.value || "TEXT").toUpperCase();
      const formatted = formatStepDataValue(textarea.value, language);
      if (formatted === null) {
        flashFormatError(formatBtn);
        return;
      }
      textarea.value = formatted;
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      expand();
      showHighlighted();
    });
  }
});
