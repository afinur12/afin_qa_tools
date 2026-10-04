// Export a Knowledge Management page or a whole section to PDF, boards laid
// out as on screen, on white paper. html2canvas renders, pdf-lib builds A4
// sheets (both vendored). Every page — the open one, or each page of a
// section — is rendered from its paper view (/knowledge/pages/<id>?paper=1)
// in a hidden iframe, so both exports look alike and nothing stays hidden in
// an editor's scroll area. The paper rules in paperClone avoid html2canvas
// pitfalls listed in the spec's "Export to PDF" section.
(function () {
  const dialog = document.querySelector("[data-km-export]");
  if (!dialog || !window.html2canvas || !window.PDFLib) return;
  const L = window.KnowledgeLayout;
  const status = dialog.querySelector("[data-km-export-status]");
  const runButton = dialog.querySelector("[data-km-export-run]");
  const DEFAULT_STATUS = "Exact layout as on screen, on white paper (A4). Text is part of the picture, so it isn't selectable.";
  // Width of the hidden paper view: the page head and the boards share one
  // scale, and a page with one small board isn't blown up to the sheet width.
  const PAPER_WIDTH = 1000;
  const LOAD_TIMEOUT = 30000;
  let target = { sectionId: "", sectionName: "" };
  let cancelled = false;

  function open(scope, sectionId, sectionName, trigger) {
    target = { sectionId, sectionName };
    // "This page" only when the open page belongs to the section being exported.
    const page = document.querySelector("[data-km-page]");
    const hasPage = Boolean(page?.dataset.kmPage) && page.dataset.kmSectionId === String(sectionId);
    dialog.querySelector('[data-km-export-option="page"]').hidden = !hasPage;
    dialog.querySelector(`input[name="km_export_scope"][value="${hasPage ? scope : "section"}"]`).checked = true;
    dialog.querySelector("[data-km-export-section-name]").textContent = sectionName;
    status.textContent = DEFAULT_STATUS;
    window.KnowledgeCanvas?.leaveOverlays();
    openModal(dialog, trigger);
  }

  document.querySelector("[data-km-export-page]")?.addEventListener("click", (event) => {
    const page = document.querySelector("[data-km-page]");
    open("page", page.dataset.kmSectionId, page.dataset.kmSectionName, event.currentTarget);
  });
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-km-export-section]");
    if (!button) return;
    event.preventDefault();
    open("section", button.dataset.kmExportSection, button.dataset.sectionName, button);
  });
  // Closing the dialog any way (Cancel, ×, Esc, the backdrop) stops a running export.
  new MutationObserver(() => {
    if (dialog.hidden) cancelled = true;
  }).observe(dialog, { attributes: true, attributeFilter: ["hidden"] });

  // ── render one page from its paper view ───────────────────────────────
  function paperClone(doc) {
    doc.documentElement.setAttribute("data-theme", "light");
    doc.querySelectorAll(".km-toolbar, .km-resize, .km-board-actions, .km-block-tools, .km-table-tools, [data-km-link-open], [data-km-link-pop], [data-km-unlink], .save-state, [data-manual-save]")
      .forEach((el) => el.remove());
    // The file card's Download button means nothing on paper. (Empty text
    // blocks' "Type here…" is switched off by the paper view's CSS: html2canvas
    // copies ::before content before this runs.)
    doc.querySelectorAll(".km-file .btn").forEach((el) => el.remove());
    doc.querySelectorAll(".km-board.is-selected").forEach((el) => el.classList.remove("is-selected"));
    // Inputs render clipped in html2canvas: on paper they are plain text.
    doc.querySelectorAll("input.km-title, input.km-board-title, input.km-caption").forEach((input) => {
      const text = doc.createElement("div");
      text.className = input.className;
      text.textContent = input.value;
      input.replaceWith(text);
    });
    // Ellipsis isn't honoured on paper — show chips in full.
    doc.querySelectorAll(".km-chip").forEach((chip) => { chip.style.maxWidth = "none"; });
    doc.querySelectorAll(".km-chip .txt").forEach((t) => { t.style.whiteSpace = "normal"; t.style.overflow = "visible"; });
    // Nothing may hide inside a scroll area (a scrollbar would eat the last row) —
    // except in a board whose height was pinned: like on screen it shows what
    // fits instead of spilling over the boards below it.
    doc.querySelectorAll(".km-board-body, .km-code .snippet-code").forEach((el) => { el.style.overflow = "visible"; });
    doc.querySelectorAll(".km-board").forEach((board) => {
      if (board.style.height) board.querySelector(".km-board-body").style.overflow = "hidden";
    });
    const wrap = doc.querySelector("[data-km-canvas-wrap]");
    if (wrap) {
      wrap.style.backgroundImage = "none";
      wrap.style.overflow = "visible";
    }
  }

  async function renderDocument(doc) {
    // A clone copies the value *attribute*; make it match the field.
    doc.querySelectorAll("input").forEach((input) => input.setAttribute("value", input.value));
    const headElement = doc.querySelector("[data-km-paper-head]");
    const boxes = [...doc.querySelectorAll("[data-km-canvas] .km-board")].map((b) => ({ id: 0, x: b.offsetLeft, y: b.offsetTop, w: b.offsetWidth, h: b.offsetHeight }));
    const width = Math.max(headElement.offsetWidth, Math.max(240, ...boxes.map((b) => b.x + b.w)) + 20);
    const height = Math.max(80, ...boxes.map((b) => b.y + b.h)) + 20;
    const scale = Math.min(2, 16000 / height); // browsers cap a canvas at ~16k px
    const options = {
      scale, backgroundColor: "#ffffff", logging: false, onclone: paperClone,
      windowWidth: doc.defaultView.innerWidth, windowHeight: Math.max(doc.documentElement.scrollHeight, height + 1500),
    };
    const head = await window.html2canvas(headElement, options);
    const body = await window.html2canvas(doc.querySelector("[data-km-canvas]"), { ...options, width, height });
    return { head, body, spans: boxes.map((b) => [b.y * scale, (b.y + b.h) * scale]) };
  }

  function loadPaper(pageId) {
    return new Promise((resolve, reject) => {
      const frame = document.createElement("iframe");
      frame.style.cssText = `position:fixed; left:-12000px; top:0; width:${PAPER_WIDTH}px; height:1000px; border:0;`;
      const timer = setTimeout(() => {
        frame.remove();
        reject(new Error("a page took too long to load"));
      }, LOAD_TIMEOUT);
      frame.onload = async () => {
        const doc = frame.contentDocument;
        await Promise.all([...doc.images].map((img) => (img.complete ? null : new Promise((done) => { img.onload = done; img.onerror = done; }))));
        clearTimeout(timer);
        if (!doc.querySelector("[data-km-paper-head]")) {
          frame.remove();
          reject(new Error("a page no longer exists"));
          return;
        }
        resolve({ doc, frame });
      };
      frame.src = `/knowledge/pages/${pageId}?paper=1`;
      document.body.appendChild(frame);
    });
  }

  // ── PDF assembly ──────────────────────────────────────────────────────
  // pdf-lib's standard fonts only cover WinAnsi (Latin-1) text.
  const pdfText = (text, fallback = "Untitled") => String(text ?? "")
    .replace(/→/g, "->").replace(/[–—•·]/g, "-").replace(/[‘’]/g, "'").replace(/[“”]/g, '"').replace(/…/g, "...")
    .replace(/[^\x20-\x7E\xA0-\xFF]/g, "").trim() || fallback;
  const fileSafe = (text) => String(text).replace(/[\\/:*?"<>|]+/g, "-").trim();

  // Shortens text with "..." until it fits maxWidth at this font size.
  function fit(text, font, size, maxWidth) {
    if (font.widthOfTextAtSize(text, size) <= maxWidth) return text;
    let cut = text;
    while (cut.length > 1 && font.widthOfTextAtSize(`${cut}...`, size) > maxWidth) cut = cut.slice(0, -1);
    return `${cut.trimEnd()}...`;
  }

  async function embedSlice(pdf, source, top, height) {
    const piece = document.createElement("canvas");
    piece.width = source.width;
    piece.height = Math.max(1, Math.round(height));
    piece.getContext("2d").drawImage(source, 0, top, source.width, height, 0, 0, source.width, height);
    return pdf.embedPng(piece.toDataURL("image/png"));
  }

  // Lays one rendered page onto as many A4 sheets as it needs; returns the
  // number of sheets used.
  async function addRenderedPage(pdf, rendered, size) {
    const [PW, PH] = size;
    const M = 28, FOOT = 22, CW = PW - 2 * M;
    let sheet = pdf.addPage(size);
    let used = 1;
    let y = PH - M;
    // The head keeps its proportions: full width, or narrower when it would be taller than 160 pt.
    const k = Math.min(CW / rendered.head.width, 160 / rendered.head.height);
    const headHeight = rendered.head.height * k;
    sheet.drawImage(await embedSlice(pdf, rendered.head, 0, rendered.head.height), { x: M, y: y - headHeight, width: rendered.head.width * k, height: headHeight });
    y -= headHeight + 8;
    const body = rendered.body;
    const scale = CW / body.width;
    let offset = 0;
    while (offset < body.height - 1) {
      const limit = Math.min(body.height, offset + Math.floor((y - M - FOOT) / scale));
      const cut = Math.max(offset + 1, limit >= body.height ? body.height : L.bestCut(offset, limit, rendered.spans));
      const image = await embedSlice(pdf, body, offset, cut - offset);
      sheet.drawImage(image, { x: M, y: y - (cut - offset) * scale, width: CW, height: (cut - offset) * scale });
      offset = cut;
      if (offset < body.height - 1) {
        sheet = pdf.addPage(size);
        used += 1;
        y = PH - M;
      }
    }
    return used;
  }

  async function addPaperPage(pdf, pageId, size) {
    const { doc, frame } = await loadPaper(pageId);
    try {
      return await addRenderedPage(pdf, await renderDocument(doc), size);
    } finally {
      frame.remove();
    }
  }

  runButton.addEventListener("click", async () => {
    const scope = dialog.querySelector('input[name="km_export_scope"]:checked').value;
    const landscape = dialog.querySelector('input[name="km_export_orientation"]:checked').value === "landscape";
    const size = landscape ? [842, 595] : [595, 842];
    const job = { ...target }; // reopening the dialog for another section mid-run can't relabel this one
    const textWidth = size[0] - 56;
    runButton.disabled = true;
    cancelled = false;
    try {
      const { PDFDocument, StandardFonts, rgb } = window.PDFLib;
      const pdf = await PDFDocument.create();
      const font = await pdf.embedFont(StandardFonts.Helvetica);
      const bold = await pdf.embedFont(StandardFonts.HelveticaBold);
      const labels = []; // footer label per sheet
      let fileName;
      if (scope === "page") {
        const page = document.querySelector("[data-km-page]");
        const title = document.querySelector("input.km-title")?.value || "Untitled page";
        status.textContent = `Rendering "${title}"…`;
        const used = await addPaperPage(pdf, page.dataset.kmPage, size);
        for (let i = 0; i < used; i++) labels.push(title);
        fileName = `${job.sectionName} - ${title}.pdf`;
      } else {
        const response = await fetch(`/knowledge/sections/${job.sectionId}/pages.json`);
        if (!response.ok) throw new Error("the section no longer exists");
        const pages = await response.json();
        let cover = pdf.addPage(size);
        labels.push("Contents");
        const sectionTitle = pdfText(job.sectionName);
        let titleSize = 30;
        while (titleSize > 16 && bold.widthOfTextAtSize(sectionTitle, titleSize) > textWidth) titleSize -= 2;
        cover.drawText(fit(sectionTitle, bold, titleSize, textWidth), { x: 28, y: size[1] - 90, size: titleSize, font: bold, color: rgb(0.1, 0.1, 0.1) });
        cover.drawText(pdfText(`Knowledge Management - exported ${new Date().toLocaleString()}`), { x: 28, y: size[1] - 115, size: 10, font, color: rgb(0.45, 0.43, 0.4) });
        cover.drawText("Pages", { x: 28, y: size[1] - 160, size: 12, font: bold });
        let lineY = size[1] - 182;
        pages.forEach((p, i) => {
          if (lineY < 50) {
            cover = pdf.addPage(size);
            labels.push("Contents");
            lineY = size[1] - 60;
          }
          cover.drawText(fit(`${i + 1}.  ${pdfText(p.title)}`, font, 11, textWidth), { x: 28, y: lineY, size: 11, font });
          lineY -= 18;
        });
        for (let i = 0; i < pages.length && !cancelled; i++) {
          status.textContent = `Rendering page ${i + 1} of ${pages.length}: "${pages[i].title}"…`;
          const used = await addPaperPage(pdf, pages[i].id, size);
          for (let k = 0; k < used; k++) labels.push(pages[i].title);
        }
        fileName = `${job.sectionName}.pdf`;
      }
      if (cancelled) {
        status.textContent = "Export cancelled.";
        return;
      }
      pdf.getPages().forEach((sheet, i) => sheet.drawText(
        fit(`${pdfText(job.sectionName)} > ${pdfText(labels[i])}  -  ${i + 1} / ${labels.length}`, font, 8, textWidth),
        { x: 28, y: 12, size: 8, font, color: rgb(0.55, 0.52, 0.47) },
      ));
      const bytes = await pdf.save();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
      link.download = fileSafe(fileName);
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 60000);
      status.textContent = `Downloaded "${link.download}" — ${labels.length} PDF page${labels.length === 1 ? "" : "s"}.`;
    } catch (error) {
      status.textContent = `Export failed: ${error.message || error}`;
    } finally {
      runButton.disabled = false;
    }
  });
})();
