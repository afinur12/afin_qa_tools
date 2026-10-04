// Knowledge Management page chrome: collapsible Sections / Pages columns
// (remembered per browser) and drag-to-reorder for both lists, using
// app.js's shared initReorder. The canvas, blocks and PDF export live in
// knowledge_canvas.js, knowledge_blocks.js and knowledge_export.js.
(function () {
  const root = document.querySelector("[data-km]");
  if (!root) return;

  const KEY = "qa-toolbox:km-collapsed";
  function loadState() {
    try {
      return JSON.parse(localStorage.getItem(KEY) || "{}");
    } catch {
      return {};
    }
  }
  function saveState(state) {
    try {
      localStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* storage unavailable — the columns just won't remember */
    }
  }

  const state = loadState();
  root.querySelectorAll("[data-km-col]").forEach((col) => col.classList.toggle("is-collapsed", Boolean(state[col.dataset.kmCol])));
  root.addEventListener("click", (event) => {
    const collapse = event.target.closest("[data-km-col-collapse]");
    const expand = event.target.closest("[data-km-col-expand]");
    if (!collapse && !expand) return;
    const col = (collapse || expand).closest("[data-km-col]");
    col.classList.toggle("is-collapsed", Boolean(collapse));
    state[col.dataset.kmCol] = Boolean(collapse);
    saveState(state);
  });

  const sections = root.querySelector("[data-km-sections]");
  if (sections) initReorder(sections, { itemSelector: ".km-section", idKey: "sectionId", indexSelector: "[data-km-index]" });
  const pages = root.querySelector("[data-km-pages]");
  if (pages) initReorder(pages, { itemSelector: ".km-page-item", idKey: "pageId", indexSelector: "[data-km-index]" });
})();
