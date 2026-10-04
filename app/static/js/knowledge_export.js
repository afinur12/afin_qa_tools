// Export a Knowledge Management page or a whole section to PDF, exactly as
// laid out on screen, on white paper. html2canvas renders, pdf-lib builds
// A4 sheets (both vendored). A section export renders each page in a hidden
// iframe (/knowledge/pages/<id>?paper=1). The paper rules in paperClone avoid
// html2canvas pitfalls listed in the spec's "Export to PDF" section.
(function () {
  const dialog = document.querySelector("[data-km-export]");
  if (!dialog || !window.html2canvas || !window.PDFLib) return;
  const L = window.KnowledgeLayout;
  const status = dialog.querySelector("[data-km-export-status]");
  const runButton = dialog.querySelector("[data-km-export-run]");
  const DEFAULT_STATUS = "Exact layout as on screen, on white paper (A4). Text is part of the picture, so it isn't selectable.";
  let target = { sectionId: "", sectionName: "" };
  let cancelled = false;

  function open(scope, sectionId, sectionName, trigger) {
    target = { sectionId, sectionName };
    const hasPage = Boolean(document.querySelector("[data-km-canvas]"));
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
  dialog.querySelector("[data-km-export-cancel]").addEventListener("click", () => {
    cancelled = true;
  });

  // ── render one page (live document or the paper iframe) ───────────────
  function paperClone(doc) {
    doc.documentElement.setAttribute("data-theme", "light");
    doc.querySelectorAll(".km-toolbar, .km-resize, .km-board-actions, .km-block-tools, .km-table-tools, [data-km-link-open], [data-km-link-pop], [data-km-unlink], .save-state, [data-manual-save]")
      .forEach((el) => el.remove());
    // Also off paper: the file card's Download button, and the "Type here…"
    // placeholder html2canvas would paint into empty text blocks.
    doc.querySelectorAll(".km-file .btn").forEach((el) => el.remove());
    doc.querySelectorAll("[data-km-text]:empty").forEach((el) => el.removeAttribute("data-placeholder"));
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
    // Nothing may hide inside a scroll area (a scrollbar would eat the last row).
    doc.querySelectorAll(".km-board-body, .km-code .snippet-code").forEach((el) => { el.style.overflow = "visible"; });
    const wrap = doc.querySelector("[data-km-canvas-wrap]");
    if (wrap) {
      wrap.style.backgroundImage = "none";
      wrap.style.overflow = "visible";
    }
  }

  async function renderDocument(doc) {
    // A clone copies the value *attribute*; make it match what's typed.
    doc.querySelectorAll("input").forEach((input) => input.setAttribute("value", input.value));
    const wrap = doc.querySelector("[data-km-canvas-wrap]");
    const scroll = [wrap.scrollLeft, wrap.scrollTop];
    wrap.scrollTo(0, 0);
    const boxes = [...doc.querySelectorAll("[data-km-canvas] .km-board")].map((b) => ({ id: 0, x: b.offsetLeft, y: b.offsetTop, w: b.offsetWidth, h: b.offsetHeight }));
    const width = Math.max(240, ...boxes.map((b) => b.x + b.w)) + 20;
    const height = Math.max(80, ...boxes.map((b) => b.y + b.h)) + 20;
    const scale = Math.min(2, 16000 / height); // browsers cap a canvas at ~16k px
    const options = {
      scale, backgroundColor: "#ffffff", logging: false, onclone: paperClone,
      windowWidth: doc.defaultView.innerWidth, windowHeight: Math.max(doc.documentElement.scrollHeight, height + 1500),
    };
    const head = await window.html2canvas(doc.querySelector("[data-km-paper-head]"), options);
    const body = await window.html2canvas(doc.querySelector("[data-km-canvas]"), { ...options, width, height });
    wrap.scrollTo(scroll[0], scroll[1]);
    return { head, body, spans: boxes.map((b) => [b.y * scale, (b.y + b.h) * scale]) };
  }

  function loadPaper(pageId) {
    return new Promise((resolve, reject) => {
      const frame = document.createElement("iframe");
      frame.style.cssText = "position:fixed; left:-12000px; top:0; width:1600px; height:1000px; border:0;";
      frame.src = `/knowledge/pages/${pageId}?paper=1`;
      frame.onload = async () => {
        const doc = frame.contentDocument;
        await Promise.all([...doc.images].map((img) => (img.complete ? null : new Promise((done) => { img.onload = done; img.onerror = done; }))));
        resolve({ doc, frame });
      };
      frame.onerror = reject;
      document.body.appendChild(frame);
    });
  }

  // ── PDF assembly ──────────────────────────────────────────────────────
  // pdf-lib's standard fonts only cover WinAnsi text.
  const ascii = (text) => String(text).replace(/→/g, "->").replace(/[–—·]/g, "-").replace(/[^\x20-\x7E]/g, "");
  const fileSafe = (text) => String(text).replace(/[\\/:*?"<>|]+/g, "-").trim() || "export.pdf";

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
    const headHeight = Math.min(rendered.head.height * (CW / rendered.head.width), 160);
    sheet.drawImage(await embedSlice(pdf, rendered.head, 0, rendered.head.height), { x: M, y: y - headHeight, width: CW, height: headHeight });
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

  runButton.addEventListener("click", async () => {
    const scope = dialog.querySelector('input[name="km_export_scope"]:checked').value;
    const landscape = dialog.querySelector('input[name="km_export_orientation"]:checked').value === "landscape";
    const size = landscape ? [842, 595] : [595, 842];
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
        const title = document.querySelector("input.km-title")?.value || "Untitled page";
        status.textContent = `Rendering "${title}"…`;
        const used = await addRenderedPage(pdf, await renderDocument(document), size);
        for (let i = 0; i < used; i++) labels.push(title);
        fileName = `${target.sectionName} - ${title}.pdf`;
      } else {
        const pages = await (await fetch(`/knowledge/sections/${target.sectionId}/pages.json`)).json();
        let cover = pdf.addPage(size);
        labels.push("Contents");
        cover.drawText(ascii(target.sectionName), { x: 28, y: size[1] - 90, size: 30, font: bold, color: rgb(0.1, 0.1, 0.1) });
        cover.drawText(ascii(`Knowledge Management - exported ${new Date().toLocaleString()}`), { x: 28, y: size[1] - 115, size: 10, font, color: rgb(0.45, 0.43, 0.4) });
        cover.drawText("Pages", { x: 28, y: size[1] - 160, size: 12, font: bold });
        let lineY = size[1] - 182;
        pages.forEach((p, i) => {
          if (lineY < 50) {
            cover = pdf.addPage(size);
            labels.push("Contents");
            lineY = size[1] - 60;
          }
          cover.drawText(ascii(`${i + 1}.  ${p.title}`), { x: 28, y: lineY, size: 11, font });
          lineY -= 18;
        });
        for (let i = 0; i < pages.length && !cancelled; i++) {
          status.textContent = `Rendering page ${i + 1} of ${pages.length}: "${pages[i].title}"…`;
          const { doc, frame } = await loadPaper(pages[i].id);
          try {
            const used = await addRenderedPage(pdf, await renderDocument(doc), size);
            for (let k = 0; k < used; k++) labels.push(pages[i].title);
          } finally {
            frame.remove();
          }
        }
        fileName = `${target.sectionName}.pdf`;
      }
      if (cancelled) {
        status.textContent = "Export cancelled.";
        return;
      }
      pdf.getPages().forEach((sheet, i) => sheet.drawText(
        ascii(`${target.sectionName} > ${labels[i] || ""}  -  ${i + 1} / ${labels.length}`),
        { x: 28, y: 12, size: 8, font, color: rgb(0.55, 0.52, 0.47) },
      ));
      const bytes = await pdf.save();
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob([bytes], { type: "application/pdf" }));
      link.download = fileSafe(fileName);
      document.body.appendChild(link);
      link.click();
      link.remove();
      status.textContent = `Downloaded "${link.download}" — ${labels.length} PDF page${labels.length === 1 ? "" : "s"}.`;
    } catch (error) {
      status.textContent = `Export failed: ${error}`;
    } finally {
      runButton.disabled = false;
    }
  });
})();
