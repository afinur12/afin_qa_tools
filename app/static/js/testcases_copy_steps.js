// "Copy steps to…" on the test case page: tick steps (their checkbox sits
// in each step header), pick a destination test case and one of its
// sections, and the server appends copies — Test Data and screenshots
// included — to that section. The selection bar itself (count + button,
// shown only while something is ticked) is app.js's generic
// [data-selection-actions] handling.
(function () {
  const root = document.querySelector("[data-copy-steps-form]");
  if (!root) return;
  const form = root.closest("form");
  const filter = root.querySelector("[data-copy-dest-filter]");
  const destSelect = root.querySelector("[data-copy-dest]");
  const sectionSelect = root.querySelector("[data-copy-section]");
  const submitBtn = form.querySelector("[data-copy-submit]");

  function tickedSteps() {
    return Array.from(document.querySelectorAll('input[data-step-select]:checked'));
  }

  // "Matching sections" sends each step into the destination section like its
  // own (no section to pick); "One section" sends them all to the section
  // picked. Opening the dialog preselects matching when the ticked steps come
  // from more than one section.
  const modeBoxes = form.querySelectorAll("[data-copy-mode]");
  const sectionField = form.querySelector("[data-copy-section-field]");
  let sectionsLoaded = false;
  const mode = () => form.querySelector("[data-copy-mode]:checked")?.value || "section";
  function applyMode() {
    const matching = mode() === "match";
    if (sectionField) sectionField.hidden = matching;
    sectionSelect.disabled = matching || !sectionsLoaded;
  }
  modeBoxes.forEach((box) => box.addEventListener("change", applyMode));

  // A destination without any sections can only take "Matching sections",
  // which creates the sections the steps come from.
  const blankNote = form.querySelector("[data-copy-blank-note]");
  const oneSectionBox = form.querySelector('[data-copy-mode][value="section"]');
  function setBlank(blank) {
    if (blankNote) blankNote.hidden = !blank;
    if (oneSectionBox) {
      oneSectionBox.disabled = blank;
      oneSectionBox.closest(".choice")?.classList.toggle("is-disabled", blank);
    }
    if (blank) modeBoxes.forEach((box) => { box.checked = box.value === "match"; });
    applyMode();
  }
  document.addEventListener("click", (event) => {
    if (!event.target.closest('[data-modal-open="copy-steps"]')) return;
    const sections = new Set(tickedSteps().map((cb) => cb.closest(".section-card")?.dataset.sectionId));
    const wanted = sections.size > 1 || oneSectionBox?.disabled ? "match" : "section";
    modeBoxes.forEach((box) => { box.checked = box.value === wanted; });
    applyMode();
  });

  // A section's box ticks every step in that section, "Select all steps"
  // every step on the page. Any tick keeps those boxes (checked, or partly
  // checked), the selection bar's count and the submit button's label in step.
  const stepBoxes = (scope) => Array.from(scope.querySelectorAll("input[data-step-select]"));
  function mirror(box, boxes) {
    const n = boxes.filter((b) => b.checked).length;
    box.checked = n > 0 && n === boxes.length;
    box.indeterminate = n > 0 && n < boxes.length;
  }
  function syncSelectBoxes() {
    document.querySelectorAll("[data-section-select]").forEach((box) => mirror(box, stepBoxes(box.closest(".section-card"))));
    document.querySelectorAll("[data-select-all-steps]").forEach((box) => mirror(box, stepBoxes(document)));
    if (submitBtn) {
      const n = tickedSteps().length;
      submitBtn.textContent = `Copy ${n} step${n === 1 ? "" : "s"}`;
    }
  }
  document.addEventListener("change", (event) => {
    const sectionBox = event.target.closest("[data-section-select]");
    const allBox = event.target.closest("[data-select-all-steps]");
    if (sectionBox) stepBoxes(sectionBox.closest(".section-card")).forEach((b) => { b.checked = sectionBox.checked; });
    else if (allBox) stepBoxes(document).forEach((b) => { b.checked = allBox.checked; });
    else if (!event.target.matches("[data-step-select]")) return;
    syncSelectBoxes();
    // app.js counts the selection on "change" as well, but ran before these
    // step boxes were set.
    if (sectionBox || allBox) syncSelectionActions();
  });
  // Back/forward cache and form restore can bring ticked boxes back.
  window.addEventListener("pageshow", syncSelectBoxes);

  // Filter the destination list by any text in its label or group.
  filter?.addEventListener("input", () => {
    const needle = filter.value.trim().toLowerCase();
    destSelect.querySelectorAll("optgroup").forEach((group) => {
      let anyVisible = false;
      group.querySelectorAll("option").forEach((option) => {
        const match = !needle || `${group.label} ${option.textContent}`.toLowerCase().includes(needle);
        option.hidden = !match;
        anyVisible = anyVisible || match;
      });
      group.hidden = !anyVisible;
    });
  });

  // Picking a test case loads its sections, numbered as on its own page.
  destSelect.addEventListener("change", async () => {
    sectionsLoaded = false;
    sectionSelect.disabled = true;
    setBlank(false);
    sectionSelect.innerHTML = '<option value="">Loading sections…</option>';
    try {
      const response = await fetch(`/testcases/${destSelect.value}/sections.json`);
      const data = await response.json();
      sectionSelect.innerHTML = "";
      if (!data.sections.length) {
        sectionSelect.innerHTML = '<option value="">This test case has no sections</option>';
        setBlank(true);
        return;
      }
      data.sections.forEach((section) => {
        const option = document.createElement("option");
        option.value = section.id;
        option.textContent = `${section.label} (${section.step_count} step${section.step_count === 1 ? "" : "s"})`;
        sectionSelect.appendChild(option);
      });
      sectionsLoaded = true;
      applyMode();
    } catch {
      sectionSelect.innerHTML = '<option value="">Couldn\'t load sections — try again</option>';
    }
  });

  // The ticked step ids live outside this form (in each step header), so
  // copy them in as hidden inputs right before it submits.
  form.addEventListener("submit", (event) => {
    form.querySelectorAll('input[data-generated="1"]').forEach((el) => el.remove());
    const ticked = tickedSteps();
    const destinationChosen = mode() === "match" ? destSelect.value : sectionSelect.value;
    if (!ticked.length || !destinationChosen) {
      event.preventDefault();
      return;
    }
    ticked.forEach((cb) => {
      const input = document.createElement("input");
      input.type = "hidden";
      input.name = "step_ids";
      input.value = cb.value;
      input.dataset.generated = "1";
      form.appendChild(input);
    });
  });
})();
