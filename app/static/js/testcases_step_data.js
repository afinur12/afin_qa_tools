// Test Case execute page: Test Data items (see the data_item_block macro in
// app/templates/testcases/execute.html). Uses the exact same live,
// always-syntax-highlighted code editor as the API Client builder's request
// body field (attachCodeEditor, in app.js) — a transparent-text textarea
// stacked on a read-only hljs overlay underneath it, so what you're typing
// is always shown in color, with no separate "click to see it highlighted"
// step. See attachCodeEditor's own comments in app.js for why it can't
// wrap (the overlay and the textarea would disagree on where a long line
// wraps, and the caret — which only ever tracks the real textarea — would
// drift away from the colored text underneath it).

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
  // Collapse this formatter's own `\<newline>` line-continuation markers
  // back to plain spaces before tokenizing, so formatting an already
  // multi-line command is idempotent instead of compounding: without this,
  // re-tokenizing a previously formatted value picked up each bare "\" as
  // its own token (it doesn't start with "-", so it fell into the catch-all
  // "give it its own line" branch below) and every re-click added another
  // layer of stray "\ \" lines. A backslash isn't touched unless it's
  // immediately followed by (optional trailing whitespace then) a newline,
  // so it never reaches into an already-quoted multi-line JSON body's own
  // newlines (those aren't preceded by a backslash).
  const normalized = text.replace(/\\\s*\r?\n\s*/g, " ");
  // Deliberately simple: splits on whitespace outside of quotes, so a flag
  // value with an escaped quote inside it won't round-trip perfectly. Good
  // enough for the curl commands QA engineers paste in by hand.
  const tokens = tokenizeCurlLike(normalized);
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

// detectSnippetLanguage only calls something JSON if it actually parses —
// exactly the case that isn't true for what the format button most needs
// to recognize: invalid or still-being-typed JSON (a trailing comma, a
// missing closing brace). Shape alone (a leading {, [, or <) is a much
// better signal of what the user was going for than strict validity, so
// the format button guesses from shape first and only falls back to the
// stricter general-purpose detector for anything that doesn't match one.
function guessFormatLanguage(text) {
  const trimmed = text.trim();
  if (/^curl\b/i.test(trimmed)) return "CURL";
  if (/^[{[]/.test(trimmed)) return "JSON";
  if (/^</.test(trimmed)) return "XML";
  if (/^(SELECT|INSERT\s+INTO|UPDATE|DELETE\s+FROM|CREATE\s+(TABLE|INDEX|VIEW)|ALTER\s+TABLE|DROP\s+TABLE|WITH)\b/i.test(trimmed)) {
    return "SQL";
  }
  return detectSnippetLanguage(text) || "TEXT";
}

// Matches the API Client request body's own beautify button (its
// data-ac-body-beautify handler in api_client.js): silently do nothing on
// empty content, and on failure show a toast naming what's wrong rather
// than just an icon flash — useful there because there's only one body
// field on the page, but Test Data can have many items in one step, so the
// icon flash is kept too, to point at which one.
const STEP_DATA_FORMAT_LANGUAGES = { JSON: "JSON", SQL: "SQL", CURL: "a curl command", XML: "XML" };
function stepDataFormatFailureMessage(language) {
  const label = STEP_DATA_FORMAT_LANGUAGES[language];
  return label ? `Not valid ${label} — can't beautify` : `No formatter for ${language} yet — can't beautify`;
}

// Named (not an inline arrow in the forEach below) so a textarea inserted
// after page load — a freshly added item, see the "+ Add Data" handling
// further down — can get the identical wiring instead of only ever working
// after the next full page reload.
function wireStepDataItem(textarea) {
  // Named codeWrapEl, not "wrap", to keep it distinct from attachCodeEditor's
  // unrelated `wrap` option (CSS word-wrap) passed in below.
  const codeWrapEl = textarea.closest("[data-step-data-code-wrap]");
  const form = textarea.closest("form");
  const languageField = form.querySelector("[data-note-language]");
  const languageLabel = form.querySelector("[data-step-data-lang-label]");
  const toggleBtn = form.querySelector("[data-step-data-toggle]");
  const formatBtn = form.querySelector("[data-step-data-format]");

  function currentLanguage() {
    return detectSnippetLanguage(textarea.value) || "TEXT";
  }

  attachCodeEditor(textarea, () => HLJS_LANGUAGE_MAP[currentLanguage()] || "plaintext", {
    wrap: true,
    onSync: () => {
      const lang = currentLanguage();
      languageField.value = lang;
      if (languageLabel) languageLabel.textContent = lang;
    },
  });

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const collapsed = form.classList.toggle("is-collapsed");
      codeWrapEl.hidden = collapsed;
      toggleBtn.setAttribute("aria-expanded", collapsed ? "false" : "true");
      // scrollHeight/measured width are meaningless while a display:none
      // ancestor hides this — force attachCodeEditor's listener to resync
      // now that it's actually visible again (same pattern api_client.js
      // uses for its modal-open and kind-toggle listeners).
      if (!collapsed) textarea.dispatchEvent(new Event("input"));
    });
  }

  if (formatBtn) {
    formatBtn.addEventListener("click", () => {
      if (!textarea.value.trim()) return; // nothing to format yet
      const language = guessFormatLanguage(textarea.value);
      const formatted = formatStepDataValue(textarea.value, language);
      if (formatted === null) {
        flashFormatError(formatBtn);
        toast(stepDataFormatFailureMessage(language), "danger");
        return;
      }
      textarea.value = formatted;
      if (form.classList.contains("is-collapsed")) {
        form.classList.remove("is-collapsed");
        codeWrapEl.hidden = false;
        if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
      }
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      textarea.focus();
    });
  }
}

document.querySelectorAll("[data-step-data-textarea]").forEach(wireStepDataItem);

// Renumbers the [n] badges (and their aria-labels) after an insert or
// removal — order_no isn't resequenced server-side when an item in the
// middle is deleted, so the display position (this function's whole
// purpose) and order_no can legitimately diverge; a full page reload
// already re-derives this fresh from loop.index, this just does the same
// thing in place.
function renumberStepDataList(list) {
  list.querySelectorAll(".step-data-block").forEach((block, i) => {
    const index = i + 1;
    const indexBadge = block.querySelector(".data-item-index");
    if (indexBadge) indexBadge.textContent = `[${index}]`;
    const toggleBtn = block.querySelector("[data-step-data-toggle]");
    if (toggleBtn) toggleBtn.setAttribute("aria-label", `Collapse or expand data item ${index}`);
    const deleteBtn = block.querySelector("[data-note-delete]");
    if (deleteBtn) deleteBtn.setAttribute("aria-label", `Remove data item ${index}`);
  });
}

// ── Add / Remove without a full page reload ───────────────────────────────
// A plain form POST+redirect (the no-JS fallback, still what create_step_
// data/delete_step_data do for a request without this header) reloads the
// whole page — collapsing every step back to its default state and losing
// scroll position, just to add or remove one Test Data item. Posting via
// fetch instead keeps the page exactly as it was.
document.querySelectorAll("[data-step-data-add-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const list = form.previousElementSibling;
    if (!list || !list.matches("[data-step-data-list]")) {
      form.submit(); // markup changed under us somehow — fall back rather than silently do nothing
      return;
    }
    let html;
    try {
      const response = await fetch(form.action, { method: "POST", headers: { "X-Requested-With": "fetch" } });
      if (!response.ok) throw new Error(`create_step_data returned ${response.status}`);
      html = await response.text();
    } catch {
      form.submit(); // network/server hiccup — the normal full-page path still works
      return;
    }
    const wrapper = document.createElement("div");
    wrapper.innerHTML = html;
    const nodes = Array.from(wrapper.children);
    nodes.forEach((node) => list.appendChild(node));
    const newBlock = nodes.find((node) => node.classList.contains("step-data-block"));
    const newTextarea = newBlock?.querySelector("[data-step-data-textarea]");
    if (newTextarea) {
      wireStepDataItem(newTextarea);
      wireAutosaveForm(newBlock);
      newTextarea.focus();
    }
  });
});

// Delegated (not one listener per delete form): "+ Add Data" can create
// new ones after page load, and a plain per-element listener wired up only
// at load time would silently miss every one of those.
document.addEventListener("submit", async (event) => {
  const form = event.target;
  if (!form.matches("[data-step-data-delete-form]")) return;
  event.preventDefault();
  const block = form.previousElementSibling; // the .step-data-block this delete form belongs to (see the macro: they're always adjacent siblings)
  const list = form.closest("[data-step-data-list]");
  try {
    const response = await fetch(form.action, { method: "POST", headers: { "X-Requested-With": "fetch" } });
    if (!response.ok) throw new Error(`delete_step_data returned ${response.status}`);
  } catch {
    form.submit(); // network/server hiccup — fall back to the normal full-page path
    return;
  }
  block?.remove();
  form.remove();
  if (list) renumberStepDataList(list);
});
