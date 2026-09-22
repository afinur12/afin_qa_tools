"""Real execution tests for the Knowledge Base card / Note markdown renderer.

The design spec (docs/superpowers/specs/2026-09-22-knowledge-base-cards-design.md)
explicitly calls for one test above all others: "a card containing literal
`<script>` text renders as escaped text, never executes." That test was never
actually written — the only prior coverage
(test_knowledge_base.py::test_app_js_markdown_renderer_supports_images_and_language_tagged_code)
only checks that certain substrings exist somewhere in the served app.js; it
never calls the function, so it would pass even if renderNoteMarkdown were
deleted and replaced with a no-op.

renderNoteMarkdown and escapeHtmlForMarkdown live in app/static/js/app.js —
plain browser JS, not something importable from Python. To actually execute
them (rather than just grep the source), this module extracts their exact
source text out of the served file and runs them under Node, via a small
inline DOM shim (Node has no `document` global). Node is not otherwise a
dependency of this repo, so every test here is skipped when `node` isn't on
PATH rather than failing the suite.
"""

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

APP_JS = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "app.js"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not available")


def _extract_function(source: str, name: str) -> str:
    """Pull the exact source text of `function <name>(...) { ... }` out of
    app.js, from the `function` keyword to the matching closing brace.

    A regex can't reliably find the matching close: the function bodies
    contain nested braces of their own (an inner helper function, and
    template-literal `${...}` expressions). Brace-counting handles that
    correctly as long as every `{`/`}` character in the source — including
    ones inside comments or strings — is itself balanced, which is true of
    both functions here (verified by hand and by this extraction round-
    tripping into syntactically valid, correctly-behaving JS below).
    """
    marker = f"function {name}("
    start = source.index(marker)
    brace_start = source.index("{", start)
    depth = 0
    i = brace_start
    while i < len(source):
        ch = source[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return source[start : i + 1]
        i += 1
    raise AssertionError(f"unbalanced braces while extracting {name!r} from app.js")


# A minimal DOM shim for the one API escapeHtmlForMarkdown actually touches:
# document.createElement("div") plus that element's .textContent/.innerHTML.
# Its only job is to reproduce real-browser text-node serialization when
# .textContent is read back via .innerHTML: `&`, `<`, `>` get entity-encoded;
# `"` and `'` are left alone by the browser itself (escapeHtmlForMarkdown's
# own `.replace(/"/g, "&quot;")` is what handles quotes, on top of this).
# This is NOT a general DOM implementation — it deliberately covers nothing
# else, because nothing else is used.
_DOM_SHIM = """
function _makeShimDiv() {
  let raw = "";
  return {
    set textContent(v) { raw = String(v); },
    get textContent() { return raw; },
    get innerHTML() {
      return raw.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    },
  };
}
const document = { createElement: () => _makeShimDiv() };
"""

# Each case below exercises renderNoteMarkdown end-to-end (which itself calls
# escapeHtmlForMarkdown internally), plus one direct call to
# escapeHtmlForMarkdown for the quote-escaping regression.
_CASES_SCRIPT = r"""
const results = {};

// 1. The spec-named invariant: a raw <script> tag must render as escaped
// text, never as a live, executable tag.
results.scriptEscaped = renderNoteMarkdown("<script>alert(1)</script>");

// 2. Regression for the quote-escaping fix (Fix 2): a crafted image
// alt/src must not produce a live onerror attribute in the output.
results.imgOnerrorAttempt = renderNoteMarkdown('![" onerror="ALERT](x)');

// 2b. escapeHtmlForMarkdown directly: quotes become &quot;, existing
// &/</> escaping is untouched.
results.escapedQuote = escapeHtmlForMarkdown('He said "hi" <b>&amp;</b>');

// 3. Basic image syntax.
results.basicImage = renderNoteMarkdown("![alt](url)");

// 4. Language-tagged fenced code.
results.taggedFence = renderNoteMarkdown("```python\nprint(1)\n```");

// 4b. Regression for the fence-lang sanitizing fix: a hostile/garbage info
// string must not leak raw into the class attribute.
results.fenceInjectionAttempt = renderNoteMarkdown('```a" onmouseover="ALERT\ncode\n```');

// 5. An untagged fence after a tagged one must not inherit its language.
results.fenceNoLeak = renderNoteMarkdown("```python\ncode1\n```\n```\nplain\n```");

// 6. Pre-existing behavior this change must not have broken: headings,
// bold, a list.
results.heading = renderNoteMarkdown("# Heading");
results.bold = renderNoteMarkdown("**bold**");
results.list = renderNoteMarkdown("- item1\n- item2");

console.log(JSON.stringify(results));
"""


def _run_node(js_source: str) -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        script_path = Path(tmp) / "run_markdown_renderer.js"
        script_path.write_text(js_source, encoding="utf-8")
        result = subprocess.run(
            ["node", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    assert result.returncode == 0, f"node script failed:\n{result.stderr}"
    return json.loads(result.stdout)


@pytest.fixture(scope="module")
def rendered():
    app_js_source = APP_JS.read_text(encoding="utf-8")
    escape_fn_src = _extract_function(app_js_source, "escapeHtmlForMarkdown")
    render_fn_src = _extract_function(app_js_source, "renderNoteMarkdown")
    script = "\n".join([_DOM_SHIM, escape_fn_src, render_fn_src, _CASES_SCRIPT])
    return _run_node(script)


def test_script_tag_renders_as_escaped_text_never_executes(rendered):
    # The one test the design spec explicitly names as required: this is the
    # security invariant the whole card/note content renderer leans on.
    html = rendered["scriptEscaped"]
    assert "<script>" not in html
    assert "</script>" not in html
    assert "&lt;script&gt;" in html
    assert "&lt;/script&gt;" in html


def test_crafted_image_alt_cannot_inject_a_live_html_attribute(rendered):
    html = rendered["imgOnerrorAttempt"]
    assert 'onerror="ALERT' not in html  # no live attribute reached the DOM
    assert "&quot;" in html  # the quote was escaped instead


def test_escape_html_for_markdown_escapes_quotes_and_html_metacharacters(rendered):
    escaped = rendered["escapedQuote"]
    assert escaped == 'He said &quot;hi&quot; &lt;b&gt;&amp;amp;&lt;/b&gt;'


def test_image_syntax_renders_img_tag(rendered):
    assert '<img src="url" alt="alt">' in rendered["basicImage"]


def test_language_tagged_fence_gets_language_class(rendered):
    assert '<pre><code class="language-python">print(1)</code></pre>' == rendered["taggedFence"]


def test_hostile_fence_info_string_cannot_inject_a_class_attribute(rendered):
    html = rendered["fenceInjectionAttempt"]
    assert 'onmouseover="ALERT' not in html
    # Only the safe leading token ("a") survives into the class name.
    assert '<pre><code class="language-a">code</code></pre>' == html


def test_untagged_fence_does_not_inherit_previous_fences_language(rendered):
    html = rendered["fenceNoLeak"]
    assert html.count("language-") == 1
    assert '<pre><code class="language-python">code1</code></pre>' in html
    assert "<pre><code>plain</code></pre>" in html


def test_heading_bold_and_list_still_render(rendered):
    assert rendered["heading"] == "<h1>Heading</h1>"
    assert rendered["bold"] == "<p><strong>bold</strong></p>"
    assert rendered["list"] == "<ul><li>item1</li><li>item2</li></ul>"
