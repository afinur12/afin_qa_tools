(function () {
  const textInput = document.getElementById("qr-text");
  if (!textInput) return;

  const eclSelect = document.getElementById("qr-ecl");
  const cellSizeInput = document.getElementById("qr-cell-size");
  const errorBox = document.getElementById("qr-error");
  const image = document.getElementById("qr-image");
  const downloadLink = document.getElementById("qr-download");

  function render() {
    const text = textInput.value;
    if (!text) {
      errorBox.textContent = "Enter some text or a URL to encode.";
      errorBox.hidden = false;
      image.hidden = true;
      downloadLink.removeAttribute("href");
      return;
    }
    try {
      // typeNumber 0 lets the library pick the smallest QR version that fits.
      const qr = window.qrcode(0, eclSelect.value);
      qr.addData(text);
      qr.make();
      const cellSize = Math.min(20, Math.max(2, parseInt(cellSizeInput.value, 10) || 6));
      const dataUrl = qr.createDataURL(cellSize, cellSize * 2);

      errorBox.hidden = true;
      image.src = dataUrl;
      image.hidden = false;
      downloadLink.href = dataUrl;
    } catch (err) {
      errorBox.textContent = `Couldn't generate a QR code: ${err.message}`;
      errorBox.hidden = false;
      image.hidden = true;
      downloadLink.removeAttribute("href");
    }
  }

  let timer;
  function scheduleRender() {
    clearTimeout(timer);
    timer = setTimeout(render, 200);
  }

  textInput.addEventListener("input", scheduleRender);
  eclSelect.addEventListener("change", render);
  cellSizeInput.addEventListener("change", render);
  render();
})();
