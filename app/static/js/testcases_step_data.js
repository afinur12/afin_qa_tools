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

document.querySelectorAll("[data-step-data-textarea]").forEach((textarea) => {
  const wrap = textarea.closest("[data-step-data-code-wrap]");
  const form = textarea.closest("form");
  const languageField = form.querySelector("[data-note-language]");
  const languageLabel = form.querySelector("[data-step-data-lang-label]");
  const toggleBtn = form.querySelector("[data-step-data-toggle]");
  const formatBtn = form.querySelector("[data-step-data-format]");

  function currentLanguage() {
    return detectSnippetLanguage(textarea.value) || "TEXT";
  }

  attachCodeEditor(textarea, () => HLJS_LANGUAGE_MAP[currentLanguage()] || "plaintext", {
    onSync: () => {
      const lang = currentLanguage();
      languageField.value = lang;
      if (languageLabel) languageLabel.textContent = lang;
    },
  });

  if (toggleBtn) {
    toggleBtn.addEventListener("click", () => {
      const collapsed = form.classList.toggle("is-collapsed");
      wrap.hidden = collapsed;
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
      const formatted = formatStepDataValue(textarea.value, currentLanguage());
      if (formatted === null) {
        flashFormatError(formatBtn);
        return;
      }
      textarea.value = formatted;
      if (form.classList.contains("is-collapsed")) {
        form.classList.remove("is-collapsed");
        wrap.hidden = false;
        if (toggleBtn) toggleBtn.setAttribute("aria-expanded", "true");
      }
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      textarea.focus();
    });
  }
});
