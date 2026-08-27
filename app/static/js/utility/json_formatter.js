(function () {
  const input = document.getElementById("json-input");
  if (!input) return;

  const output = document.getElementById("json-output");
  const errorBox = document.getElementById("json-error");
  const indentSelect = document.getElementById("json-indent");
  const sortKeysInput = document.getElementById("json-sort-keys");
  const copyBtn = document.getElementById("json-copy");
  const prettifyBtn = document.getElementById("json-prettify");
  const minifyBtn = document.getElementById("json-minify");

  function sortKeysDeep(value) {
    if (Array.isArray(value)) return value.map(sortKeysDeep);
    if (value && typeof value === "object") {
      const sorted = {};
      Object.keys(value)
        .sort()
        .forEach((key) => {
          sorted[key] = sortKeysDeep(value[key]);
        });
      return sorted;
    }
    return value;
  }

  function indentValue() {
    const raw = indentSelect.value;
    return raw === "tab" ? "\t" : parseInt(raw, 10);
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    output.textContent = "";
    output.classList.add("empty");
    copyBtn.dataset.copyText = "";
  }

  function showOutput(text) {
    errorBox.hidden = true;
    output.textContent = text;
    output.classList.remove("empty");
    copyBtn.dataset.copyText = text;
  }

  let lastMode = "prettify";

  function run(mode) {
    lastMode = mode;
    const raw = input.value.trim();
    if (!raw) {
      showError("Nothing to format — paste some JSON above.");
      return;
    }
    let parsed;
    try {
      parsed = JSON.parse(raw);
    } catch (err) {
      showError(`Invalid JSON: ${err.message}`);
      return;
    }
    if (sortKeysInput.checked) parsed = sortKeysDeep(parsed);
    const text = mode === "minify" ? JSON.stringify(parsed) : JSON.stringify(parsed, null, indentValue());
    showOutput(text);
  }

  prettifyBtn.addEventListener("click", () => run("prettify"));
  minifyBtn.addEventListener("click", () => run("minify"));
  indentSelect.addEventListener("change", () => run(lastMode));
  sortKeysInput.addEventListener("change", () => run(lastMode));

  run("prettify");
})();
