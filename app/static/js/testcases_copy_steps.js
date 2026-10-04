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

  // Keep the submit button's label in step with the ticked boxes.
  document.addEventListener("change", (event) => {
    if (!event.target.matches("[data-step-select]") || !submitBtn) return;
    const n = tickedSteps().length;
    submitBtn.textContent = `Copy ${n} step${n === 1 ? "" : "s"}`;
  });

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
    sectionSelect.disabled = true;
    sectionSelect.innerHTML = '<option value="">Loading sections…</option>';
    try {
      const response = await fetch(`/testcases/${destSelect.value}/sections.json`);
      const data = await response.json();
      sectionSelect.innerHTML = "";
      if (!data.sections.length) {
        sectionSelect.innerHTML = '<option value="">This test case has no sections</option>';
        return;
      }
      data.sections.forEach((section) => {
        const option = document.createElement("option");
        option.value = section.id;
        option.textContent = `${section.label} (${section.step_count} step${section.step_count === 1 ? "" : "s"})`;
        sectionSelect.appendChild(option);
      });
      sectionSelect.disabled = false;
    } catch {
      sectionSelect.innerHTML = '<option value="">Couldn\'t load sections — try again</option>';
    }
  });

  // The ticked step ids live outside this form (in each step header), so
  // copy them in as hidden inputs right before it submits.
  form.addEventListener("submit", (event) => {
    form.querySelectorAll('input[data-generated="1"]').forEach((el) => el.remove());
    const ticked = tickedSteps();
    if (!ticked.length || !sectionSelect.value) {
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
