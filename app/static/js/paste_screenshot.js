// Paste a screenshot into a step's drop zone.
//
// The upload used to finish with window.location.reload(), which threw the
// viewport back to the top of a long execution page every time — and, because
// the reload sat inside the loop over clipboard items, a paste carrying more
// than one image only ever saved the first. The thumbnail is now inserted
// straight into the page, so nothing scrolls and every pasted image is kept.

// The icon_eye(16) and icon_trash(13) macros (macros.html).
const EYE_ICON = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
const TRASH_ICON = '<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6M14 11v6"/></svg>';

// Same markup as a thumbnail the page was rendered with (testcases/execute.html),
// so a pasted screenshot looks and behaves the same straight away: click it to
// view it, trash icon to remove it.
function thumbnailFor(screenshot, stepNumber) {
  const wrapper = document.createElement("div");
  wrapper.className = "shot";
  wrapper.innerHTML = `
    <button type="button" class="shot-view" data-shot-view>
      <img>
      <span class="shot-view-overlay" aria-hidden="true">${EYE_ICON}</span>
    </button>
    <form method="post" style="margin-top:5px;">
      <button class="btn act remove" type="submit" style="width:100%;" title="Remove screenshot" aria-label="Remove screenshot">${TRASH_ICON}</button>
    </form>`;
  wrapper.querySelector("[data-shot-view]").setAttribute("aria-label", `View screenshot for step ${stepNumber}`);
  const image = wrapper.querySelector("img");
  image.src = screenshot.url;
  image.alt = `Screenshot for step ${stepNumber}`;
  wrapper.querySelector("form").action = `/screenshots/${screenshot.id}/delete`;
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
