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

// A pasted image shows at once as a tile that fills up while it uploads
// (window.Progress, progress.js), says "Saving…" while the server stores it,
// then becomes the real thumbnail. A failed upload keeps its tile with a
// Retry button.
function pendingTile(file, stepNumber) {
  const tile = document.createElement("div");
  tile.className = "shot is-uploading";
  tile.innerHTML = `
    <div class="shot-view">
      <img>
      <div class="shot-progress" aria-live="polite"><span>0%</span></div>
    </div>
    <div style="margin-top:5px;">
      <button class="btn act remove" type="button" style="width:100%;" disabled></button>
    </div>`;
  const image = tile.querySelector("img");
  image.src = URL.createObjectURL(file);
  image.alt = `Screenshot for step ${stepNumber}, uploading`;
  tile.querySelector(".shot-progress").appendChild(window.Progress.makeBar());
  return tile;
}

async function uploadTile(tile, file, uploadUrl, stepNumber) {
  const P = window.Progress;
  const label = tile.querySelector(".shot-progress span");
  const bar = tile.querySelector(".shot-progress .pbar");
  const button = tile.querySelector("button");
  tile.className = "shot is-uploading";
  label.textContent = "0%";
  P.setBar(bar, 0);
  button.className = "btn act remove";
  button.disabled = true;
  button.innerHTML = '<span class="spin" aria-hidden="true"></span>';
  button.title = "Uploading…";
  button.setAttribute("aria-label", "Uploading");
  button.onclick = null;

  const formData = new FormData();
  formData.append("file", file, `pasted.${(file.type.split("/")[1] || "png")}`);
  P.begin();
  try {
    const result = await P.upload(uploadUrl, formData, {
      accept: "application/json",
      onProgress(loaded, total) {
        const pct = P.percent(loaded, total);
        if (pct !== null && pct < 100) {
          label.textContent = `${pct}%`;
          P.setBar(bar, pct);
        } else {
          label.textContent = "Saving…";
          P.setBar(bar, "working");
        }
      },
    });
    if (result.status !== 200) throw new Error(String(result.status));
    URL.revokeObjectURL(tile.querySelector("img").src);
    tile.replaceWith(thumbnailFor(JSON.parse(result.text), stepNumber));
  } catch {
    tile.className = "shot is-failed";
    label.textContent = "Upload failed";
    button.className = "btn act retry";
    button.disabled = false;
    button.textContent = "Retry";
    button.title = "Try the upload again";
    button.setAttribute("aria-label", "Retry the upload");
    button.onclick = () => uploadTile(tile, file, uploadUrl, stepNumber);
  } finally {
    P.end();
  }
}

document.querySelectorAll(".dropzone[data-step-id]").forEach((zone) => {
  zone.addEventListener("click", () => zone.focus());

  zone.addEventListener("paste", async (event) => {
    const items = event.clipboardData ? Array.from(event.clipboardData.items) : [];
    const images = items.filter((item) => item.type.startsWith("image/"));
    if (!images.length) return;

    // Stop the image from also being pasted as content into any focused field.
    event.preventDefault();

    const testcaseId = window.location.pathname.split("/")[2];
    const uploadUrl = `/testcases/${testcaseId}/steps/${zone.dataset.stepId}/screenshot`;
    const stepNumber = zone.closest(".step")?.querySelector(".step-no")?.textContent?.trim() ?? "";

    // Every tile appears at once; they upload one after another, in order.
    const queue = images.map((item) => item.getAsFile()).filter(Boolean)
      .map((file) => ({ file, tile: shotsContainer(zone).appendChild(pendingTile(file, stepNumber)) }));
    for (const { file, tile } of queue) await uploadTile(tile, file, uploadUrl, stepNumber);
  });
});
