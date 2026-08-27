(function () {
  const expressionInput = document.getElementById("jp-expression");
  if (!expressionInput) return;

  const jsonInput = document.getElementById("jp-input");
  const resultBox = document.getElementById("jp-result");
  const errorBox = document.getElementById("jp-error");
  const copyBtn = document.getElementById("jp-copy");

  function evaluate() {
    if (!window.jmespath) {
      errorBox.textContent = "JMESPath library failed to load.";
      errorBox.hidden = false;
      return;
    }

    let data;
    try {
      data = JSON.parse(jsonInput.value);
    } catch (err) {
      errorBox.textContent = `Invalid input JSON: ${err.message}`;
      errorBox.hidden = false;
      resultBox.textContent = "";
      resultBox.classList.add("empty");
      copyBtn.dataset.copyText = "";
      return;
    }

    try {
      const value = window.jmespath.search(data, expressionInput.value);
      const text = value === undefined ? "null" : JSON.stringify(value, null, 2);
      errorBox.hidden = true;
      resultBox.textContent = text;
      resultBox.classList.remove("empty");
      copyBtn.dataset.copyText = text;
    } catch (err) {
      errorBox.textContent = err.message;
      errorBox.hidden = false;
      resultBox.textContent = "";
      resultBox.classList.add("empty");
      copyBtn.dataset.copyText = "";
    }
  }

  let timer;
  function scheduleEvaluate() {
    clearTimeout(timer);
    timer = setTimeout(evaluate, 200);
  }

  expressionInput.addEventListener("input", scheduleEvaluate);
  jsonInput.addEventListener("input", scheduleEvaluate);
  evaluate();
})();
