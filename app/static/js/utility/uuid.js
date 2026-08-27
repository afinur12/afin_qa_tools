(function () {
  const list = document.getElementById("uuid-list");
  if (!list) return;

  const countInput = document.getElementById("uuid-count");
  const upperInput = document.getElementById("uuid-uppercase");
  const noHyphenInput = document.getElementById("uuid-no-hyphens");
  const generateBtn = document.getElementById("uuid-generate");
  const copyAllBtn = document.getElementById("uuid-copy-all");

  function format(id) {
    const value = noHyphenInput.checked ? id.replace(/-/g, "") : id;
    return upperInput.checked ? value.toUpperCase() : value;
  }

  function render() {
    const count = Math.min(200, Math.max(1, parseInt(countInput.value, 10) || 1));
    countInput.value = count;
    const ids = Array.from({ length: count }, () => format(crypto.randomUUID()));

    list.innerHTML = "";
    ids.forEach((id) => {
      const row = document.createElement("div");
      row.className = "uuid-row";

      const span = document.createElement("span");
      span.textContent = id;

      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "btn act edit";
      btn.dataset.copy = "";
      btn.dataset.copyText = id;
      btn.title = "Copy UUID";
      btn.setAttribute("aria-label", "Copy UUID");
      btn.innerHTML =
        '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>' +
        '<span class="sr-only" data-copy-label>Copy</span>';

      row.appendChild(span);
      row.appendChild(btn);
      list.appendChild(row);
    });

    copyAllBtn.dataset.copyText = ids.join("\n");
  }

  generateBtn.addEventListener("click", render);
  countInput.addEventListener("change", render);
  upperInput.addEventListener("change", render);
  noHyphenInput.addEventListener("change", render);
  render();
})();
