(function () {
  const input = document.getElementById("py-input");
  if (!input) return;

  const output = document.getElementById("py-output");
  const errorBox = document.getElementById("py-error");
  const copyBtn = document.getElementById("py-copy-output");
  const runBtn = document.getElementById("py-run");

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
  }

  function showResult(stdout, error) {
    output.textContent = stdout || "";
    output.classList.toggle("empty", !stdout);
    copyBtn.dataset.copyText = stdout || "";
    if (error) {
      showError(error);
    } else {
      errorBox.hidden = true;
    }
  }

  async function run() {
    const code = input.value;
    runBtn.disabled = true;
    try {
      const resp = await fetch("/utility/python-runner/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      if (!resp.ok) {
        showResult("", `Request failed (HTTP ${resp.status}).`);
        return;
      }
      const data = await resp.json();
      showResult(data.stdout, data.error);
    } catch (err) {
      showResult("", `Couldn't reach the server: ${err.message}`);
    } finally {
      runBtn.disabled = false;
    }
  }

  runBtn.addEventListener("click", run);
})();
