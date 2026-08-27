(function () {
  const fileInput = document.getElementById("pdf-edit-file");
  if (!fileInput) return;

  const editorBox = document.getElementById("pdf-editor");
  const hint = document.getElementById("pdf-edit-hint");
  const thumbStrip = document.getElementById("pdf-thumb-strip");
  const canvasWrap = document.getElementById("pdf-canvas-wrap");
  const canvas = document.getElementById("pdf-editor-canvas");
  const annotLayer = document.getElementById("pdf-annot-layer");
  const addTextBtn = document.getElementById("pdf-add-text");
  const addCoverBtn = document.getElementById("pdf-add-cover");
  const sizeInput = document.getElementById("pdf-annot-size");
  const colorInput = document.getElementById("pdf-annot-color");
  const applyBtn = document.getElementById("pdf-edit-apply");
  const errorBox = document.getElementById("pdf-error");

  const sigPad = document.getElementById("pdf-signature-pad");
  const sigCtx = sigPad.getContext("2d");
  const sigClearBtn = document.getElementById("pdf-signature-clear");
  const sigInsertBtn = document.getElementById("pdf-signature-insert");

  const MAIN_WIDTH = 680;
  const THUMB_WIDTH = 130;

  let pdfDoc = null; // pdfjsLib document
  let pdfBytes = null; // original ArrayBuffer, kept for export
  let pages = []; // [{ uid, originalIndex, rotationDelta, annotations: [] }]
  let uidCounter = 0;
  let activeUid = null;
  let coverMode = false;

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function activePage() {
    return pages.find((p) => p.uid === activeUid) || null;
  }

  function scaleForWidth(pageWidthPt, targetWidth) {
    return targetWidth / pageWidthPt;
  }

  // ── Loading a file ─────────────────────────────────────────────────────
  fileInput.addEventListener("change", async () => {
    const file = fileInput.files[0];
    if (!file) return;
    errorBox.hidden = true;
    try {
      pdfBytes = await file.arrayBuffer();
      pdfDoc = await window.pdfjsLib.getDocument({ data: pdfBytes.slice(0) }).promise;

      pages = [];
      for (let i = 0; i < pdfDoc.numPages; i += 1) {
        pages.push({ uid: uidCounter++, originalIndex: i, rotationDelta: 0, annotations: [] });
      }
      activeUid = pages[0].uid;
      hint.hidden = true;
      editorBox.hidden = false;
      await renderThumbnails();
      await renderMain();
    } catch (err) {
      showError(`Couldn't open that PDF: ${err.message}`);
    }
  });

  // ── Thumbnails (visual page manager) ────────────────────────────────────
  async function renderThumbnails() {
    thumbStrip.innerHTML = "";
    for (let i = 0; i < pages.length; i += 1) {
      const entry = pages[i];
      const pdfPage = await pdfDoc.getPage(entry.originalIndex + 1);
      const base = pdfPage.getViewport({ scale: 1 });
      const scale = scaleForWidth(base.width, THUMB_WIDTH);
      const viewport = pdfPage.getViewport({ scale });

      const thumbCanvas = document.createElement("canvas");
      thumbCanvas.width = viewport.width;
      thumbCanvas.height = viewport.height;
      await pdfPage.render({ canvasContext: thumbCanvas.getContext("2d"), viewport }).promise;
      if (entry.rotationDelta) thumbCanvas.style.transform = `rotate(${entry.rotationDelta}deg)`;

      const box = document.createElement("div");
      box.className = "pdf-page-thumb" + (entry.uid === activeUid ? " active" : "");
      box.dataset.uid = String(entry.uid);
      box.appendChild(thumbCanvas);

      const label = document.createElement("div");
      label.className = "pdf-thumb-label";
      label.textContent = `Page ${i + 1}`;
      box.appendChild(label);

      const controls = document.createElement("div");
      controls.className = "pdf-thumb-controls";
      controls.appendChild(thumbButton("↑", "Move up", i === 0, () => movePage(entry.uid, -1)));
      controls.appendChild(thumbButton("↓", "Move down", i === pages.length - 1, () => movePage(entry.uid, 1)));
      controls.appendChild(thumbButton("⟳", "Rotate 90°", false, () => rotatePage(entry.uid)));
      controls.appendChild(thumbButton("⧉", "Duplicate", false, () => duplicatePage(entry.uid)));
      controls.appendChild(thumbButton("×", "Delete page", pages.length <= 1, () => deletePage(entry.uid)));
      box.appendChild(controls);

      box.addEventListener("click", (event) => {
        if (event.target.closest("button")) return;
        activeUid = entry.uid;
        renderThumbnails();
        renderMain();
      });

      thumbStrip.appendChild(box);
    }
  }

  function thumbButton(label, title, disabled, onClick) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = label;
    btn.title = title;
    btn.setAttribute("aria-label", title);
    btn.disabled = disabled;
    btn.addEventListener("click", (event) => {
      event.stopPropagation();
      onClick();
    });
    return btn;
  }

  function movePage(uid, direction) {
    const index = pages.findIndex((p) => p.uid === uid);
    const target = index + direction;
    if (target < 0 || target >= pages.length) return;
    [pages[index], pages[target]] = [pages[target], pages[index]];
    renderThumbnails();
  }

  function rotatePage(uid) {
    const entry = pages.find((p) => p.uid === uid);
    entry.rotationDelta = (entry.rotationDelta + 90) % 360;
    renderThumbnails();
  }

  function duplicatePage(uid) {
    const index = pages.findIndex((p) => p.uid === uid);
    const source = pages[index];
    const clone = {
      uid: uidCounter++,
      originalIndex: source.originalIndex,
      rotationDelta: source.rotationDelta,
      annotations: source.annotations.map((a) => ({ ...a })),
    };
    pages.splice(index + 1, 0, clone);
    renderThumbnails();
  }

  function deletePage(uid) {
    if (pages.length <= 1) return;
    const index = pages.findIndex((p) => p.uid === uid);
    pages.splice(index, 1);
    if (activeUid === uid) activeUid = pages[Math.min(index, pages.length - 1)].uid;
    renderThumbnails();
    renderMain();
  }

  // ── Main editing canvas ──────────────────────────────────────────────────
  let currentScale = 1;
  let currentPageHeightPt = 0;

  async function renderMain() {
    const entry = activePage();
    if (!entry) return;
    const pdfPage = await pdfDoc.getPage(entry.originalIndex + 1);
    const base = pdfPage.getViewport({ scale: 1 });
    currentScale = scaleForWidth(base.width, MAIN_WIDTH);
    currentPageHeightPt = base.height;
    const viewport = pdfPage.getViewport({ scale: currentScale });

    canvas.width = viewport.width;
    canvas.height = viewport.height;
    annotLayer.style.width = `${viewport.width}px`;
    annotLayer.style.height = `${viewport.height}px`;
    await pdfPage.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

    renderAnnotations();
  }

  function renderAnnotations() {
    annotLayer.innerHTML = "";
    const entry = activePage();
    if (!entry) return;
    entry.annotations.forEach((annot) => annotLayer.appendChild(buildAnnotEl(annot)));
  }

  function buildAnnotEl(annot) {
    const el = document.createElement("div");
    el.className = "pdf-annot" + (annot.cover ? " cover" : "");
    el.style.left = `${annot.leftPx}px`;
    el.style.top = `${annot.topPx}px`;
    el.style.width = `${annot.widthPx}px`;
    el.style.height = `${annot.heightPx}px`;

    const grip = document.createElement("div");
    grip.className = "pdf-annot-grip";
    grip.dataset.drag = "";
    grip.textContent = "⠿";
    el.appendChild(grip);

    const del = document.createElement("button");
    del.type = "button";
    del.className = "pdf-annot-del";
    del.title = "Remove";
    del.setAttribute("aria-label", "Remove annotation");
    del.textContent = "×";
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      const entry = activePage();
      entry.annotations = entry.annotations.filter((a) => a !== annot);
      renderAnnotations();
    });
    el.appendChild(del);

    if (annot.type === "text") {
      const textarea = document.createElement("textarea");
      textarea.className = "pdf-annot-text";
      textarea.value = annot.text;
      textarea.style.fontSize = `${annot.fontSizePt * currentScale}px`;
      textarea.style.color = annot.color;
      textarea.addEventListener("input", () => {
        annot.text = textarea.value;
      });
      textarea.addEventListener("pointerdown", (event) => event.stopPropagation());
      el.appendChild(textarea);
    } else if (annot.type === "image") {
      const img = document.createElement("img");
      img.className = "pdf-annot-img";
      img.src = annot.dataUrl;
      el.appendChild(img);
    }

    const resize = document.createElement("div");
    resize.className = "pdf-annot-resize";
    resize.dataset.resize = "";
    el.appendChild(resize);

    attachDragResize(el, grip, resize, annot);
    return el;
  }

  function attachDragResize(el, grip, resizeHandle, annot) {
    let mode = null;
    let startX = 0;
    let startY = 0;
    let startLeft = 0;
    let startTop = 0;
    let startW = 0;
    let startH = 0;

    function onPointerMove(event) {
      const dx = event.clientX - startX;
      const dy = event.clientY - startY;
      if (mode === "drag") {
        annot.leftPx = startLeft + dx;
        annot.topPx = startTop + dy;
      } else if (mode === "resize") {
        annot.widthPx = Math.max(24, startW + dx);
        annot.heightPx = Math.max(16, startH + dy);
      }
      el.style.left = `${annot.leftPx}px`;
      el.style.top = `${annot.topPx}px`;
      el.style.width = `${annot.widthPx}px`;
      el.style.height = `${annot.heightPx}px`;
    }

    function onPointerUp() {
      mode = null;
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    }

    function start(newMode) {
      return (event) => {
        event.preventDefault();
        mode = newMode;
        startX = event.clientX;
        startY = event.clientY;
        startLeft = annot.leftPx;
        startTop = annot.topPx;
        startW = annot.widthPx;
        startH = annot.heightPx;
        window.addEventListener("pointermove", onPointerMove);
        window.addEventListener("pointerup", onPointerUp);
      };
    }

    grip.addEventListener("pointerdown", start("drag"));
    resizeHandle.addEventListener("pointerdown", start("resize"));
  }

  // ── Adding annotations ───────────────────────────────────────────────────
  let addOffset = 0;

  function addTextAnnotation(cover) {
    const entry = activePage();
    if (!entry) return;
    addOffset = (addOffset + 24) % 120;
    const annot = {
      type: "text",
      cover,
      text: cover ? "" : "New text",
      fontSizePt: parseInt(sizeInput.value, 10) || 14,
      color: colorInput.value,
      leftPx: 40 + addOffset,
      topPx: 40 + addOffset,
      widthPx: 160,
      heightPx: 32,
    };
    entry.annotations.push(annot);
    renderAnnotations();
  }

  addTextBtn.addEventListener("click", () => addTextAnnotation(false));
  addCoverBtn.addEventListener("click", () => {
    coverMode = !coverMode;
    addCoverBtn.classList.toggle("active", coverMode);
    if (coverMode) addTextAnnotation(true);
    coverMode = false;
    addCoverBtn.classList.remove("active");
  });

  // ── Signature pad ────────────────────────────────────────────────────────
  let drawing = false;
  let lastPoint = null;

  function sigPointerPos(event) {
    const rect = sigPad.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * sigPad.width,
      y: ((event.clientY - rect.top) / rect.height) * sigPad.height,
    };
  }

  sigPad.addEventListener("pointerdown", (event) => {
    drawing = true;
    lastPoint = sigPointerPos(event);
  });
  sigPad.addEventListener("pointermove", (event) => {
    if (!drawing) return;
    const point = sigPointerPos(event);
    sigCtx.strokeStyle = "#1b1b19";
    sigCtx.lineWidth = 2.5;
    sigCtx.lineCap = "round";
    sigCtx.beginPath();
    sigCtx.moveTo(lastPoint.x, lastPoint.y);
    sigCtx.lineTo(point.x, point.y);
    sigCtx.stroke();
    lastPoint = point;
  });
  window.addEventListener("pointerup", () => {
    drawing = false;
  });

  sigClearBtn.addEventListener("click", () => {
    sigCtx.clearRect(0, 0, sigPad.width, sigPad.height);
  });

  sigInsertBtn.addEventListener("click", () => {
    const entry = activePage();
    if (!entry) return;
    const dataUrl = sigPad.toDataURL("image/png");
    entry.annotations.push({
      type: "image",
      dataUrl,
      leftPx: 60,
      topPx: 60,
      widthPx: 180,
      heightPx: 74,
    });
    renderAnnotations();
    sigCtx.clearRect(0, 0, sigPad.width, sigPad.height);
  });

  // ── Apply & download ─────────────────────────────────────────────────────
  function hexToRgb(hex) {
    const clean = hex.replace("#", "");
    const num = parseInt(clean, 16);
    return {
      r: ((num >> 16) & 255) / 255,
      g: ((num >> 8) & 255) / 255,
      b: (num & 255) / 255,
    };
  }

  function positionFor(place, pageWidth, pageHeight, textWidth, fontSize) {
    const margin = 24;
    switch (place) {
      case "bottom-right": return { x: pageWidth - margin - textWidth, y: margin };
      case "bottom-left": return { x: margin, y: margin };
      case "top-right": return { x: pageWidth - margin - textWidth, y: pageHeight - margin - fontSize };
      case "top-left": return { x: margin, y: pageHeight - margin - fontSize };
      default: return { x: (pageWidth - textWidth) / 2, y: margin }; // bottom-center
    }
  }

  applyBtn.addEventListener("click", async () => {
    errorBox.hidden = true;
    if (!pdfBytes) {
      showError("Load a PDF first.");
      return;
    }
    try {
      const PDFLib = window.PDFLib;
      const srcDoc = await PDFLib.PDFDocument.load(pdfBytes.slice(0));
      const outDoc = await PDFLib.PDFDocument.create();
      const font = await outDoc.embedFont(PDFLib.StandardFonts.Helvetica);

      const watermark = document.getElementById("wm-enabled").checked
        ? {
            text: document.getElementById("wm-text").value,
            size: parseInt(document.getElementById("wm-size").value, 10) || 48,
            color: hexToRgb(document.getElementById("wm-color").value),
            opacity: parseFloat(document.getElementById("wm-opacity").value) || 0.25,
            rotation: parseInt(document.getElementById("wm-rotation").value, 10) || 0,
          }
        : null;

      const pageNumbers = document.getElementById("pn-enabled").checked
        ? {
            format: document.getElementById("pn-format").value || "Page {n} of {total}",
            position: document.getElementById("pn-position").value,
            size: parseInt(document.getElementById("pn-size").value, 10) || 10,
            start: parseInt(document.getElementById("pn-start").value, 10) || 1,
          }
        : null;

      const embeddedImages = new Map(); // dataUrl -> embedded image (avoid re-embedding duplicates)
      const total = pages.length;

      for (let i = 0; i < pages.length; i += 1) {
        const entry = pages[i];
        const [copiedPage] = await outDoc.copyPages(srcDoc, [entry.originalIndex]);
        outDoc.addPage(copiedPage);

        if (entry.rotationDelta) {
          const current = copiedPage.getRotation().angle;
          copiedPage.setRotation(PDFLib.degrees(current + entry.rotationDelta));
        }

        const { width, height } = copiedPage.getSize();
        const scale = scaleForWidth(width, MAIN_WIDTH);

        for (const annot of entry.annotations) {
          const wPt = annot.widthPx / scale;
          const hPt = annot.heightPx / scale;
          const xPt = annot.leftPx / scale;
          const yPt = height - annot.topPx / scale - hPt;

          if (annot.type === "text") {
            if (annot.cover) {
              copiedPage.drawRectangle({ x: xPt, y: yPt, width: wPt, height: hPt, color: PDFLib.rgb(1, 1, 1) });
            }
            if (annot.text) {
              const rgb = hexToRgb(annot.color);
              copiedPage.drawText(annot.text, {
                x: xPt + 2,
                y: yPt + hPt - annot.fontSizePt,
                size: annot.fontSizePt,
                font,
                color: PDFLib.rgb(rgb.r, rgb.g, rgb.b),
                maxWidth: wPt - 4,
                lineHeight: annot.fontSizePt * 1.15,
              });
            }
          } else if (annot.type === "image") {
            let img = embeddedImages.get(annot.dataUrl);
            if (!img) {
              img = await outDoc.embedPng(annot.dataUrl);
              embeddedImages.set(annot.dataUrl, img);
            }
            copiedPage.drawImage(img, { x: xPt, y: yPt, width: wPt, height: hPt });
          }
        }

        if (watermark) {
          // A long string or large font can render wider than the page itself,
          // especially once rotated — shrink it to fit so it never lands
          // (partly or fully) off-page and ends up invisible.
          const maxTextWidth = Math.min(width, height) * 0.85;
          let size = watermark.size;
          let textWidth = font.widthOfTextAtSize(watermark.text, size);
          if (textWidth > maxTextWidth) {
            size = Math.max(6, size * (maxTextWidth / textWidth));
            textWidth = font.widthOfTextAtSize(watermark.text, size);
          }
          copiedPage.drawText(watermark.text, {
            x: width / 2 - textWidth / 2,
            y: height / 2,
            size,
            font,
            color: PDFLib.rgb(watermark.color.r, watermark.color.g, watermark.color.b),
            opacity: watermark.opacity,
            rotate: PDFLib.degrees(watermark.rotation),
          });
        }

        if (pageNumbers) {
          const label = pageNumbers.format
            .replace("{n}", String(i + pageNumbers.start))
            .replace("{total}", String(total));
          const labelWidth = font.widthOfTextAtSize(label, pageNumbers.size);
          const pos = positionFor(pageNumbers.position, width, height, labelWidth, pageNumbers.size);
          copiedPage.drawText(label, { x: pos.x, y: pos.y, size: pageNumbers.size, font });
        }
      }

      const outBytes = await outDoc.save();
      const blob = new Blob([outBytes], { type: "application/pdf" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "edited.pdf";
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 4000);
    } catch (err) {
      showError(`Couldn't build the edited PDF: ${err.message}`);
    }
  });
})();
