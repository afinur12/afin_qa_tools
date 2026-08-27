(function () {
  const errorBox = document.getElementById("pdf-error");
  if (!errorBox) return;

  // ── Tabs ────────────────────────────────────────────────────────────────
  document.querySelectorAll("[data-pdf-tab]").forEach((tabButton) => {
    tabButton.addEventListener("click", () => {
      document.querySelectorAll("[data-pdf-tab]").forEach((b) => b.classList.remove("active"));
      tabButton.classList.add("active");
      const target = tabButton.dataset.pdfTab;
      document.querySelectorAll("[data-pdf-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.pdfPanel !== target;
      });
      errorBox.hidden = true;
    });
  });

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function download(bytes, filename) {
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 4000);
  }

  // Parses "1-3,5,8-9" into 0-based page indices, validated against pageCount.
  function parseRange(text, pageCount) {
    const trimmed = text.trim();
    if (!trimmed) return Array.from({ length: pageCount }, (_, i) => i);

    const indices = [];
    for (const part of trimmed.split(",")) {
      const piece = part.trim();
      if (!piece) continue;
      const rangeMatch = piece.match(/^(\d+)\s*-\s*(\d+)$/);
      if (rangeMatch) {
        const start = parseInt(rangeMatch[1], 10);
        const end = parseInt(rangeMatch[2], 10);
        if (start < 1 || end > pageCount || start > end) {
          throw new Error(`Page range "${piece}" is out of bounds (document has ${pageCount} pages).`);
        }
        for (let p = start; p <= end; p += 1) indices.push(p - 1);
      } else if (/^\d+$/.test(piece)) {
        const page = parseInt(piece, 10);
        if (page < 1 || page > pageCount) {
          throw new Error(`Page ${page} is out of bounds (document has ${pageCount} pages).`);
        }
        indices.push(page - 1);
      } else {
        throw new Error(`Couldn't parse "${piece}" as a page number or range.`);
      }
    }
    if (!indices.length) throw new Error("No valid pages given.");
    return indices;
  }

  function requireLib() {
    if (!window.PDFLib) throw new Error("PDF library failed to load.");
  }

  // ── Merge ───────────────────────────────────────────────────────────────
  const mergeFilesInput = document.getElementById("pdf-merge-files");
  const mergeList = document.getElementById("pdf-merge-list");
  const mergeRunBtn = document.getElementById("pdf-merge-run");
  let mergeFiles = [];

  function renderMergeList() {
    mergeList.innerHTML = "";
    mergeFiles.forEach((file, index) => {
      const row = document.createElement("div");
      row.className = "uuid-row";

      const span = document.createElement("span");
      span.textContent = `${index + 1}. ${file.name}`;

      const controls = document.createElement("div");
      controls.className = "row";
      controls.style.gap = "4px";

      const up = document.createElement("button");
      up.type = "button";
      up.className = "btn act edit";
      up.title = "Move up";
      up.setAttribute("aria-label", `Move ${file.name} up`);
      up.disabled = index === 0;
      up.textContent = "↑";
      up.addEventListener("click", () => {
        [mergeFiles[index - 1], mergeFiles[index]] = [mergeFiles[index], mergeFiles[index - 1]];
        renderMergeList();
      });

      const down = document.createElement("button");
      down.type = "button";
      down.className = "btn act edit";
      down.title = "Move down";
      down.setAttribute("aria-label", `Move ${file.name} down`);
      down.disabled = index === mergeFiles.length - 1;
      down.textContent = "↓";
      down.addEventListener("click", () => {
        [mergeFiles[index + 1], mergeFiles[index]] = [mergeFiles[index], mergeFiles[index + 1]];
        renderMergeList();
      });

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "btn act remove";
      remove.title = "Remove";
      remove.setAttribute("aria-label", `Remove ${file.name}`);
      remove.textContent = "×";
      remove.addEventListener("click", () => {
        mergeFiles.splice(index, 1);
        renderMergeList();
      });

      controls.appendChild(up);
      controls.appendChild(down);
      controls.appendChild(remove);
      row.appendChild(span);
      row.appendChild(controls);
      mergeList.appendChild(row);
    });
  }

  mergeFilesInput.addEventListener("change", () => {
    mergeFiles = mergeFiles.concat(Array.from(mergeFilesInput.files));
    mergeFilesInput.value = "";
    renderMergeList();
  });

  mergeRunBtn.addEventListener("click", async () => {
    errorBox.hidden = true;
    try {
      requireLib();
      if (mergeFiles.length < 2) throw new Error("Add at least two PDF files to merge.");
      const merged = await window.PDFLib.PDFDocument.create();
      for (const file of mergeFiles) {
        const bytes = await file.arrayBuffer();
        const doc = await window.PDFLib.PDFDocument.load(bytes);
        const pages = await merged.copyPages(doc, doc.getPageIndices());
        pages.forEach((page) => merged.addPage(page));
      }
      download(await merged.save(), "merged.pdf");
    } catch (err) {
      showError(err.message);
    }
  });

  // ── Split / extract ────────────────────────────────────────────────────
  const splitFileInput = document.getElementById("pdf-split-file");
  const splitRangeInput = document.getElementById("pdf-split-range");
  const splitRunBtn = document.getElementById("pdf-split-run");

  splitRunBtn.addEventListener("click", async () => {
    errorBox.hidden = true;
    try {
      requireLib();
      const file = splitFileInput.files[0];
      if (!file) throw new Error("Choose a PDF file first.");
      const bytes = await file.arrayBuffer();
      const doc = await window.PDFLib.PDFDocument.load(bytes);
      const indices = parseRange(splitRangeInput.value, doc.getPageCount());
      const out = await window.PDFLib.PDFDocument.create();
      const pages = await out.copyPages(doc, indices);
      pages.forEach((page) => out.addPage(page));
      download(await out.save(), "extracted.pdf");
    } catch (err) {
      showError(err.message);
    }
  });

  // ── Rotate ──────────────────────────────────────────────────────────────
  const rotateFileInput = document.getElementById("pdf-rotate-file");
  const rotateDegreesSelect = document.getElementById("pdf-rotate-degrees");
  const rotateRangeInput = document.getElementById("pdf-rotate-range");
  const rotateRunBtn = document.getElementById("pdf-rotate-run");

  rotateRunBtn.addEventListener("click", async () => {
    errorBox.hidden = true;
    try {
      requireLib();
      const file = rotateFileInput.files[0];
      if (!file) throw new Error("Choose a PDF file first.");
      const bytes = await file.arrayBuffer();
      const doc = await window.PDFLib.PDFDocument.load(bytes);
      const indices = parseRange(rotateRangeInput.value, doc.getPageCount());
      const amount = parseInt(rotateDegreesSelect.value, 10);
      indices.forEach((i) => {
        const page = doc.getPage(i);
        const current = page.getRotation().angle;
        page.setRotation(window.PDFLib.degrees(current + amount));
      });
      download(await doc.save(), "rotated.pdf");
    } catch (err) {
      showError(err.message);
    }
  });
})();
