(function () {
  const result = document.getElementById("diff-result");
  if (!result) return;

  const original = document.getElementById("diff-original");
  const changed = document.getElementById("diff-changed");
  const mode = document.getElementById("diff-mode");
  const compareBtn = document.getElementById("diff-compare");

  const DIFF_FN = {
    lines: (a, b) => window.Diff.diffLines(a, b),
    words: (a, b) => window.Diff.diffWordsWithSpace(a, b),
    chars: (a, b) => window.Diff.diffChars(a, b),
  };

  function render() {
    if (!window.Diff) {
      result.textContent = "Diff library failed to load.";
      return;
    }
    const parts = (DIFF_FN[mode.value] || DIFF_FN.lines)(original.value, changed.value);

    result.innerHTML = "";
    parts.forEach((part) => {
      const span = document.createElement("span");
      if (part.added) span.className = "diff-add";
      else if (part.removed) span.className = "diff-del";
      span.textContent = part.value;
      result.appendChild(span);
    });
  }

  compareBtn.addEventListener("click", render);
  mode.addEventListener("change", render);
})();
