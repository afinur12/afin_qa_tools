// Paste a screenshot into a step's drop zone.
//
// The upload used to finish with window.location.reload(), which threw the
// viewport back to the top of a long execution page every time — and, because
// the reload sat inside the loop over clipboard items, a paste carrying more
// than one image only ever saved the first. The thumbnail is now inserted
// straight into the page, so nothing scrolls and every pasted image is kept.

function thumbnailFor(screenshot, stepNumber) {
  const wrapper = document.createElement("div");
  wrapper.className = "shot";

  const image = document.createElement("img");
  image.src = screenshot.url;
  image.alt = `Screenshot for step ${stepNumber}`;
  wrapper.appendChild(image);

  const form = document.createElement("form");
  form.method = "post";
  form.action = `/screenshots/${screenshot.id}/delete`;
  form.style.marginTop = "5px";

  const button = document.createElement("button");
  button.className = "btn danger sm";
  button.type = "submit";
  button.style.cssText = "width:100%; padding:3px 6px; font-size:11px;";
  button.textContent = "Remove";

  form.appendChild(button);
  wrapper.appendChild(form);
  return wrapper;
}

function shotsContainer(zone) {
  let shots = zone.querySelector(".shots");
  if (!shots) {
    shots = document.createElement("div");
    shots.className = "shots";
    zone.insertBefore(shots, zone.firstChild);
  }
  return shots;
}

function setHint(zone, text) {
  const hint = zone.querySelector(".dropzone-hint");
  if (hint) hint.textContent = text;
}

const DEFAULT_HINT = "Click here, then press Ctrl+V to paste a screenshot.";

document.querySelectorAll(".dropzone[data-step-id]").forEach((zone) => {
  zone.addEventListener("click", () => zone.focus());

  zone.addEventListener("paste", async (event) => {
    const items = event.clipboardData ? Array.from(event.clipboardData.items) : [];
    const images = items.filter((item) => item.type.startsWith("image/"));
    if (!images.length) return;

    // Stop the image from also being pasted as content into any focused field.
    event.preventDefault();

    const stepId = zone.dataset.stepId;
    const testcaseId = window.location.pathname.split("/")[2];
    const stepNumber = zone.closest(".step")?.querySelector(".step-no")?.textContent?.trim() ?? "";

    setHint(zone, images.length > 1 ? `Uploading ${images.length} images…` : "Uploading…");

    let failed = 0;
    for (const item of images) {
      const file = item.getAsFile();
      if (!file) continue;

      const formData = new FormData();
      formData.append("file", file, `pasted.${item.type.split("/")[1]}`);

      try {
        const response = await fetch(`/testcases/${testcaseId}/steps/${stepId}/screenshot`, {
          method: "POST",
          body: formData,
          headers: { Accept: "application/json" },
        });
        if (!response.ok) throw new Error(String(response.status));
        const screenshot = await response.json();
        shotsContainer(zone).appendChild(thumbnailFor(screenshot, stepNumber));
      } catch {
        failed += 1;
      }
    }

    setHint(zone, failed ? `${failed} image(s) failed to upload — try again.` : DEFAULT_HINT);
  });
});
