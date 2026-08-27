(function () {
  const input = document.getElementById("sql-input");
  if (!input) return;

  const output = document.getElementById("sql-output");
  const errorBox = document.getElementById("sql-error");
  const dialect = document.getElementById("sql-dialect");
  const keywordCase = document.getElementById("sql-keyword-case");
  const indent = document.getElementById("sql-indent");
  const formatBtn = document.getElementById("sql-format");
  const copyBtn = document.getElementById("sql-copy");

  function run() {
    if (!window.sqlFormatter) {
      errorBox.textContent = "SQL formatter library failed to load.";
      errorBox.hidden = false;
      return;
    }
    const raw = input.value.trim();
    if (!raw) {
      errorBox.textContent = "Nothing to format — paste some SQL above.";
      errorBox.hidden = false;
      output.textContent = "";
      output.classList.add("empty");
      copyBtn.dataset.copyText = "";
      return;
    }
    try {
      const text = window.sqlFormatter.format(raw, {
        language: dialect.value,
        keywordCase: keywordCase.value,
        tabWidth: parseInt(indent.value, 10),
      });
      errorBox.hidden = true;
      output.textContent = text;
      output.classList.remove("empty");
      copyBtn.dataset.copyText = text;
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
    }
  }

  formatBtn.addEventListener("click", run);
  dialect.addEventListener("change", run);
  keywordCase.addEventListener("change", run);
  indent.addEventListener("change", run);

  run();
})();
