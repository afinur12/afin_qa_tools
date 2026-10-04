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
  // ── links to tasks and subtasks ───────────────────────────────────────
  // app.js's escapeHtml doesn't escape quotes; these strings also go into
  // attributes.
  const esc = (value) => String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const chipHtml = (link) =>
    `<span class="km-chip" data-link-id="${link.id}"><a href="${esc(link.url)}"><span class="kind">${esc(link.kind)}</span>` +
    `<span class="txt">${esc(link.code)} · ${esc(link.title)}</span></a>` +
    `<button type="button" data-km-unlink title="Unlink" aria-label="Unlink ${esc(link.code)}">&times;</button></span>`;

  const links = document.querySelector("[data-km-links]");
  if (links) {
    const pop = links.querySelector("[data-km-link-pop]");
    const search = links.querySelector("[data-km-link-search]");
    const results = links.querySelector("[data-km-link-results]");
    let timer;

    async function loadTargets() {
      const response = await fetch(`/knowledge/link-targets.json?q=${encodeURIComponent(search.value)}`);
      const data = await response.json();
      const group = (label, type, items) => (items.length
        ? `<div class="km-link-group">${label}</div>` + items.map((t) =>
          `<button type="button" class="km-link-option" data-target-type="${type}" data-target-id="${t.id}"><code>${esc(t.code)}</code> ${esc(t.title)}</button>`).join("")
        : "");
      results.innerHTML = group("Tasks", "STORY", data.stories) + group("Subtasks", "SUBTASK", data.subtasks) || '<p class="km-link-empty">Nothing matches.</p>';
    }

    links.addEventListener("click", async (event) => {
      if (event.target.closest("[data-km-link-open]")) {
        pop.hidden = !pop.hidden;
        if (!pop.hidden) {
          search.value = "";
          loadTargets();
          search.focus();
        }
        return;
      }
      const option = event.target.closest(".km-link-option");
      if (option) {
        const body = new FormData();
        body.append("page_id", links.dataset.pageId);
        body.append("target_type", option.dataset.targetType);
        body.append("target_id", option.dataset.targetId);
        const response = await fetch("/knowledge/links", { method: "POST", body, headers: { "X-Requested-With": "fetch" } });
        if (!response.ok) {
          toast("Couldn't link that item.", "danger");
          return;
        }
        const link = await response.json();
        if (!links.querySelector(`[data-link-id="${link.id}"]`)) links.querySelector("[data-km-link-open]").insertAdjacentHTML("beforebegin", chipHtml(link));
        pop.hidden = true;
        return;
      }
      const unlink = event.target.closest("[data-km-unlink]");
      if (unlink) {
        event.preventDefault();
        const chip = unlink.closest("[data-link-id]");
        const response = await fetch(`/knowledge/links/${chip.dataset.linkId}/delete`, { method: "POST", headers: { "X-Requested-With": "fetch" } });
        if (response.ok) chip.remove();
      }
    });
    search.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(loadTargets, 200);
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest("[data-km-links]")) pop.hidden = true;
    });
  }

  // ── leaving the page flushes pending edits ────────────────────────────
  // app.js saves 700 ms after typing stops or when the field loses focus;
  // closing the tab, reloading or following a link inside that window would
  // drop the edit. Forms touched in the last moments are sent once more with
  // keepalive (saving is idempotent).
  const kmPage = document.querySelector("[data-km-page]");
  if (kmPage && kmPage.dataset.kmPage) {
    const recent = new Map(); // form -> timer that forgets it
    kmPage.addEventListener("input", (event) => {
      const form = event.target.closest("form[data-autosave]");
      if (!form) return;
      clearTimeout(recent.get(form));
      recent.set(form, setTimeout(() => recent.delete(form), 2000));
    });
    const flush = () => {
      recent.forEach((timer, form) => {
        clearTimeout(timer);
        fetch(form.action, { method: "POST", body: new FormData(form), keepalive: true, headers: { "X-Requested-With": "fetch" } }).catch(() => {});
      });
      recent.clear();
    };
    window.addEventListener("pagehide", flush);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") flush();
    });
    // Enter in the page title leaves the field (which saves) instead of
    // submitting the form and reloading the page.
    kmPage.querySelector("input.km-title")?.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" || event.isComposing) return;
      event.preventDefault();
      event.target.blur();
    });
  }
})();
