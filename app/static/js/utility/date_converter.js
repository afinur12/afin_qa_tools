(function () {
  const input = document.getElementById("dt-input");
  if (!input) return;

  const output = document.getElementById("dt-output");
  const errorBox = document.getElementById("dt-error");
  const nowBtn = document.getElementById("dt-now");
  const tzSelect = document.getElementById("dt-timezone");

  const FALLBACK_ZONES = [
    "UTC", "Asia/Jakarta", "Asia/Singapore", "Asia/Tokyo", "Asia/Shanghai",
    "Asia/Kolkata", "Asia/Dubai", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "America/New_York", "America/Chicago", "America/Denver", "America/Los_Angeles",
    "Australia/Sydney",
  ];
  const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
  const zones = typeof Intl.supportedValuesOf === "function" ? Intl.supportedValuesOf("timeZone") : FALLBACK_ZONES;

  [browserZone, ...zones.filter((z) => z !== browserZone)].forEach((zone, index) => {
    const option = document.createElement("option");
    option.value = zone;
    option.textContent = index === 0 ? `${zone} (this browser)` : zone;
    tzSelect.appendChild(option);
  });

  function parseInput(raw) {
    const trimmed = raw.trim();
    if (!trimmed || trimmed.toLowerCase() === "now") return new Date();
    if (/^-?\d+$/.test(trimmed)) {
      const num = parseInt(trimmed, 10);
      // 10-digit numbers are Unix seconds; 13-digit are milliseconds.
      const ms = Math.abs(num) >= 1e12 ? num : num * 1000;
      return new Date(ms);
    }
    const parsed = new Date(trimmed);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  function relativeTime(date) {
    const diffMs = date.getTime() - Date.now();
    const diffSec = diffMs / 1000;
    const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
    const units = [
      ["year", 31536000], ["month", 2592000], ["day", 86400],
      ["hour", 3600], ["minute", 60], ["second", 1],
    ];
    for (const [unit, secondsInUnit] of units) {
      if (Math.abs(diffSec) >= secondsInUnit || unit === "second") {
        return rtf.format(Math.round(diffSec / secondsInUnit), unit);
      }
    }
    return rtf.format(0, "second");
  }

  function row(label, value) {
    const div = document.createElement("div");
    div.className = "dt-row";
    div.innerHTML = `<span class="dt-row-label">${label}</span><span class="dt-row-value">${value}</span>`;
    return div;
  }

  function render() {
    const date = parseInput(input.value);
    if (!date) {
      errorBox.textContent = "Couldn't parse that as a date, ISO string, or Unix timestamp.";
      errorBox.hidden = false;
      output.innerHTML = "";
      return;
    }
    errorBox.hidden = true;

    const zone = tzSelect.value || browserZone;
    const zoned = new Intl.DateTimeFormat("en-US", {
      timeZone: zone, dateStyle: "full", timeStyle: "long",
    }).format(date);
    const dayOfWeek = new Intl.DateTimeFormat("en-US", { weekday: "long", timeZone: zone }).format(date);

    output.innerHTML = "";
    output.appendChild(row("ISO 8601 (UTC)", date.toISOString()));
    output.appendChild(row("Unix timestamp (seconds)", Math.floor(date.getTime() / 1000)));
    output.appendChild(row("Unix timestamp (ms)", date.getTime()));
    output.appendChild(row("UTC", date.toUTCString()));
    output.appendChild(row(`Local (${zone})`, zoned));
    output.appendChild(row("Day of week", dayOfWeek));
    output.appendChild(row("Relative", relativeTime(date)));
  }

  nowBtn.addEventListener("click", () => {
    input.value = "now";
    render();
  });
  input.addEventListener("input", render);
  tzSelect.addEventListener("change", render);

  input.value = "now";
  render();
})();
