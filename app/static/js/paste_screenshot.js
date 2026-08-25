document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".dropzone[data-step-id]").forEach((zone) => {
    zone.addEventListener("click", () => zone.focus());
    zone.addEventListener("paste", async (event) => {
      const items = event.clipboardData ? event.clipboardData.items : [];
      for (const item of items) {
        if (item.type.startsWith("image/")) {
          const file = item.getAsFile();
          const formData = new FormData();
          formData.append("file", file, "pasted." + item.type.split("/")[1]);
          const stepId = zone.dataset.stepId;
          const testcaseId = window.location.pathname.split("/")[2];
          await fetch(`/testcases/${testcaseId}/steps/${stepId}/screenshot`, { method: "POST", body: formData });
          window.location.reload();
        }
      }
    });
  });
});
