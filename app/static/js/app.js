// Copy-to-clipboard for curl snippets.
document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-copy]");
  if (!button) return;

  const block = button.closest(".code-block");
  const body = block && block.querySelector(".code-body");
  if (!body) return;

  const text = body.textContent;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    // Clipboard API needs a secure context; fall back to a hidden textarea.
    const scratch = document.createElement("textarea");
    scratch.value = text;
    scratch.setAttribute("readonly", "");
    scratch.style.position = "fixed";
    scratch.style.opacity = "0";
    document.body.appendChild(scratch);
    scratch.select();
    document.execCommand("copy");
    document.body.removeChild(scratch);
  }

  const label = button.querySelector("[data-copy-label]");
  const original = label.textContent;
  label.textContent = "Copied";
  button.classList.add("copied");
  setTimeout(() => {
    label.textContent = original;
    button.classList.remove("copied");
  }, 1400);
});
