// Loading and progress for uploads, imports and downloads. One progress bar
// everywhere: a real percentage where the browser can measure it (bytes sent
// or received), an animated "working" bar with elapsed time while the server
// does its part (importing a file, building Word documents). A thin bar runs
// along the top of the page while anything is in progress.
//
// Used through window.Progress by paste_screenshot.js (screenshot tiles),
// knowledge_blocks.js (board uploads) and knowledge_export.js (PDF), and
// wired here for every import dialog (form[data-progress-upload], set by the
// modal() macro for file uploads) and every download (a[data-download],
// form[data-download]).
(function (root) {
  // ── pure helpers (tests/test_progress_js.py runs these under Node) ─────
  function formatBytes(bytes) {
    if (bytes < 1024) return `${Math.round(bytes)} B`;
    if (bytes < 1048576) return `${Math.round(bytes / 1024)} KB`;
    return `${(bytes / 1048576).toFixed(1)} MB`;
  }

  function clock(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  }

  // The file name a download should be saved under: the UTF-8 name
  // (filename*=UTF-8''...) when the server sends one, else the plain one.
  function filenameFromDisposition(header, fallback = "download") {
    if (!header) return fallback;
    const utf8 = /filename\*\s*=\s*utf-8''([^;]+)/i.exec(header);
    if (utf8) {
      try {
        return decodeURIComponent(utf8[1].trim());
      } catch {
        // malformed escape: fall back to the plain name
      }
    }
    const plain = /filename\s*=\s*(?:"([^"]*)"|([^;]+))/i.exec(header);
    const name = plain && (plain[1] ?? plain[2]);
    return (name && name.trim()) || fallback;
  }

  function percent(loaded, total) {
    return total > 0 ? Math.min(100, Math.round((loaded / total) * 100)) : null;
  }

  const api = { formatBytes, clock, filenameFromDisposition, percent };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
    return;
  }

  // ── the top bar: shown while anything is running ──────────────────────
  let running = 0;
  let topbar = null;
  function begin() {
    running += 1;
    if (!topbar) {
      topbar = document.createElement("div");
      topbar.className = "progress-topbar";
      topbar.setAttribute("aria-hidden", "true");
      topbar.innerHTML = "<i></i>";
      document.body.appendChild(topbar);
    }
    topbar.hidden = false;
  }
  function end() {
    running = Math.max(0, running - 1);
    if (topbar && running === 0) topbar.hidden = true;
  }

  // ── one bar, four states ──────────────────────────────────────────────
  function makeBar() {
    const bar = document.createElement("div");
    bar.className = "pbar";
    bar.innerHTML = "<i></i>";
    return bar;
  }
  // state: a number (0–100), "working", "done" or "failed".
  function setBar(bar, state) {
    bar.classList.remove("is-working", "is-done", "is-failed");
    const fill = bar.firstElementChild;
    if (typeof state === "number") {
      fill.style.width = `${state}%`;
    } else {
      fill.style.width = "";
      bar.classList.add(`is-${state}`);
    }
  }

  // ── a button that is busy: spinner + label, can't be clicked twice ────
  function busyButton(button, label) {
    if (!button || button.dataset.busyLabel !== undefined) return;
    button.dataset.busyLabel = button.innerHTML;
    button.dataset.busyDisabled = button.disabled ? "1" : "";
    button.disabled = true;
    button.classList.add("is-busy");
    button.setAttribute("aria-busy", "true");
    // An icon-only button (.btn.act) keeps its size: just the spinner.
    const text = label && !button.classList.contains("act") ? `<span>${label}</span>` : "";
    button.innerHTML = `<span class="spin" aria-hidden="true"></span>${text}`;
  }
  function freeButton(button) {
    if (!button || button.dataset.busyLabel === undefined) return;
    button.innerHTML = button.dataset.busyLabel;
    button.disabled = button.dataset.busyDisabled === "1";
    button.classList.remove("is-busy");
    button.removeAttribute("aria-busy");
    delete button.dataset.busyLabel;
    delete button.dataset.busyDisabled;
  }
  // A link can't be disabled: it is marked busy and further clicks ignored.
  const isBusy = (el) => el?.classList.contains("is-busy");

  // ── upload with progress (XMLHttpRequest: fetch can't report it) ──────
  // Resolves with {status, url, text, headers(name)} once the server has
  // answered (redirects already followed); rejects on a network error or
  // when `signal` aborts.
  function upload(url, body, { onProgress, accept, headers = {}, signal } = {}) {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);
      if (accept) xhr.setRequestHeader("Accept", accept);
      Object.entries(headers).forEach(([name, value]) => xhr.setRequestHeader(name, value));
      xhr.upload.onprogress = (event) => onProgress?.(event.loaded, event.lengthComputable ? event.total : 0);
      xhr.upload.onload = () => onProgress?.(1, 1);
      xhr.onload = () => resolve({
        status: xhr.status, url: xhr.responseURL, text: xhr.responseText,
        headers: (name) => xhr.getResponseHeader(name),
      });
      xhr.onerror = () => reject(new Error("network"));
      xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
      signal?.addEventListener("abort", () => xhr.abort());
      xhr.send(body);
    });
  }

  // ── the tray: one card per download (bottom right) ────────────────────
  let tray = null;
  const ICONS = {
    run: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v12M7 10l5 5 5-5M5 21h14"/></svg>',
    up: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 21V9M7 14l5-5 5 5M5 3h14"/></svg>',
    done: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12l5 5 9-10"/></svg>',
    fail: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" aria-hidden="true"><path d="M12 7v6M12 17h.01"/></svg>',
  };
  function job(title, { icon = "run", onCancel } = {}) {
    if (!tray) {
      tray = document.createElement("div");
      tray.className = "progress-tray";
      tray.setAttribute("aria-live", "polite");
      document.body.appendChild(tray);
    }
    const card = document.createElement("div");
    card.className = "progress-job";
    card.innerHTML = `<div class="progress-job-head"><div class="progress-job-icon">${ICONS[icon]}</div>`
      + '<div class="progress-job-text"><div class="progress-job-title"></div><div class="progress-job-sub"></div></div>'
      + '<button class="progress-job-x" type="button" aria-label="Cancel" title="Cancel">&times;</button></div>';
    card.querySelector(".progress-job-title").textContent = title;
    const sub = card.querySelector(".progress-job-sub");
    const bar = makeBar();
    card.appendChild(bar);
    tray.appendChild(card);
    let timer = null;
    let finished = false;
    const stopTimer = () => { clearInterval(timer); timer = null; };
    const remove = () => { stopTimer(); card.remove(); };
    card.querySelector(".progress-job-x").addEventListener("click", () => (finished ? remove() : onCancel?.()));
    const finish = (kind, text, linger) => {
      finished = true;
      stopTimer();
      card.classList.add(`is-${kind}`);
      card.querySelector(".progress-job-icon").innerHTML = ICONS[kind === "done" ? "done" : "fail"];
      card.querySelector(".progress-job-x").setAttribute("aria-label", "Dismiss");
      card.querySelector(".progress-job-x").title = "Dismiss";
      setBar(bar, kind === "done" ? "done" : "failed");
      sub.textContent = text;
      if (linger) setTimeout(remove, linger);
    };
    return {
      // The server is working: elapsed time, moving bar.
      working(label) {
        stopTimer();
        const started = Date.now();
        const tick = () => { sub.textContent = `${label} · ${clock((Date.now() - started) / 1000)}`; };
        setBar(bar, "working");
        tick();
        timer = setInterval(tick, 500);
      },
      // Bytes moving: a real percentage when the size is known.
      bytes(verb, loaded, total) {
        stopTimer();
        const pct = percent(loaded, total);
        if (pct === null) {
          setBar(bar, "working");
          sub.textContent = `${verb} · ${formatBytes(loaded)}`;
        } else {
          setBar(bar, pct);
          sub.textContent = `${verb} · ${formatBytes(loaded)} of ${formatBytes(total)} · ${pct}%`;
        }
      },
      done: (text) => finish("done", text, 4500),
      failed: (text) => finish("failed", text, 0),
      cancelled: () => finish("failed", "Cancelled", 1500),
      remove,
    };
  }

  // ── downloads: a[data-download], form[data-download] ──────────────────
  // Fetched in the background so the tray can show "Preparing on the
  // server" and then the download itself; the file is saved under the name
  // the server gives it. A page instead of a file (a redirect carrying a
  // message, e.g. "nothing to export") is opened so the message shows.
  async function download({ url, method = "GET", body = null, title, button }) {
    const controller = new AbortController();
    const card = job(title, { onCancel: () => controller.abort() });
    begin();
    busyButton(button, "Preparing…");
    try {
      card.working("Preparing on the server");
      const response = await fetch(url, { method, body, signal: controller.signal });
      const type = response.headers.get("content-type") || "";
      if (!response.ok) {
        card.failed(`Couldn't prepare the file (the server answered ${response.status}). Try again.`);
        return;
      }
      if (type.startsWith("text/html")) {
        card.remove();
        window.location.assign(response.url);
        return;
      }
      const total = Number(response.headers.get("content-length")) || 0;
      const chunks = [];
      let loaded = 0;
      if (response.body?.getReader) {
        const reader = response.body.getReader();
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          chunks.push(value);
          loaded += value.length;
          card.bytes("Downloading", loaded, total);
        }
      } else {
        chunks.push(new Uint8Array(await response.arrayBuffer()));
      }
      const name = filenameFromDisposition(response.headers.get("content-disposition"), "download");
      const link = document.createElement("a");
      link.href = URL.createObjectURL(new Blob(chunks, { type: type || "application/octet-stream" }));
      link.download = name;
      document.body.appendChild(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(link.href), 60000);
      card.done(`Saved ${name}`);
    } catch (error) {
      if (error.name === "AbortError") card.cancelled();
      else card.failed("Couldn't download the file. Check that the app is still running, then try again.");
    } finally {
      freeButton(button);
      end();
    }
  }

  const downloadTitle = (el) => el.dataset.download || el.getAttribute("title") || el.textContent.trim() || "Download";

  document.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-download]");
    if (!link || event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.shiftKey) return;
    event.preventDefault();
    if (isBusy(link)) return;
    download({ url: link.href, title: downloadTitle(link), button: link });
  });

  document.addEventListener("submit", (event) => {
    const form = event.target;
    if (event.defaultPrevented) return;
    if (form.matches("form[data-download]")) {
      event.preventDefault();
      const button = event.submitter || form.querySelector('[type="submit"]');
      const data = new FormData(form);
      const method = (form.getAttribute("method") || "GET").toUpperCase();
      let url = form.action;
      if (method === "GET") {
        const target = new URL(form.action, window.location.href);
        new URLSearchParams(data).forEach((value, key) => target.searchParams.append(key, value));
        url = target.href;
      }
      // A dialog that only chose options closes; the tray takes over.
      const dialog = form.closest("[data-modal]");
      if (dialog && typeof closeModal === "function") closeModal(dialog);
      download({ url, method, body: method === "GET" ? null : data, title: downloadTitle(form), button: dialog ? null : button });
      return;
    }
    if (form.matches("form[data-progress-upload]")) {
      event.preventDefault();
      uploadForm(form, event.submitter || form.querySelector('[type="submit"]'));
    }
  });

  // ── import dialogs: form[data-progress-upload] ────────────────────────
  // The file goes up in the background with its upload percentage shown in
  // the dialog, then "Importing… 0:04" while the server works. The server
  // answers with a redirect (to the updated page, or the import preview);
  // the page then opens it, so its message shows as usual.
  function uploadForm(form, button) {
    if (form.dataset.uploading) return;
    const file = [...form.querySelectorAll('input[type="file"]')].map((input) => input.files[0]).find(Boolean);
    if (!file && form.querySelector('input[type="file"][required]')) {
      form.reportValidity();
      return;
    }
    form.dataset.uploading = "1";
    let box = form.querySelector(".upload-progress");
    if (!box) {
      box = document.createElement("div");
      box.className = "upload-progress";
      box.setAttribute("aria-live", "polite");
      box.append(makeBar(), Object.assign(document.createElement("div"), { className: "upload-progress-line" }));
      const actions = form.querySelector(".form-actions");
      form.insertBefore(box, actions || null);
    }
    box.hidden = false;
    const bar = box.querySelector(".pbar");
    const line = box.querySelector(".upload-progress-line");
    const label = file ? file.name : "the file";
    const controller = new AbortController();
    const cancel = form.querySelector("[data-modal-close]");
    const onCancel = () => controller.abort();
    cancel?.addEventListener("click", onCancel, { once: true });
    let timer = null;
    begin();
    busyButton(button, "Uploading…");
    const show = (text, num) => { line.innerHTML = ""; line.append(Object.assign(document.createElement("span"), { textContent: text }), Object.assign(document.createElement("span"), { className: "num", textContent: num || "" })); };
    show(`Uploading ${label}`, "");
    upload(form.action, new FormData(form), {
      signal: controller.signal,
      onProgress(loaded, total) {
        const pct = percent(loaded, total);
        if (pct !== null && pct < 100) {
          setBar(bar, pct);
          show(`Uploading ${label}`, `${formatBytes(loaded)} of ${formatBytes(total)} · ${pct}%`);
          return;
        }
        // All sent: the server is importing. Cancel can't undo that now.
        if (timer) return;
        cancel?.removeEventListener("click", onCancel);
        if (cancel) cancel.disabled = true;
        busyButton(button, "Importing…");
        const started = Date.now();
        setBar(bar, "working");
        const tick = () => show(`Importing ${label}`, clock((Date.now() - started) / 1000));
        tick();
        timer = setInterval(tick, 500);
      },
    }).then((result) => {
      clearInterval(timer);
      if (result.status >= 400) throw new Error(String(result.status));
      setBar(bar, "done");
      show("Done. Opening the result…", "");
      window.location.assign(result.url);
    }).catch((error) => {
      clearInterval(timer);
      setBar(bar, "failed");
      if (error.name === "AbortError") show("Upload cancelled. Nothing was imported.", "");
      else show(/^\d+$/.test(error.message)
        ? `The server couldn't import ${label} (error ${error.message}).`
        : "Couldn't reach the app. Check that it is still running, then try again.", "");
      freeButton(button);
      if (cancel) cancel.disabled = false;
      delete form.dataset.uploading;
      end();
    });
  }

  root.Progress = { ...api, begin, end, makeBar, setBar, busyButton, freeButton, upload, job, download };
})(typeof window !== "undefined" ? window : globalThis);
