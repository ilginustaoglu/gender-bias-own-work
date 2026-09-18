const fileInput = document.getElementById("file-input");
const uploadLabel = document.querySelector(".upload");
const emptyState = document.getElementById("empty-state");
const resultsEl = document.getElementById("results");
const statusEl = document.getElementById("status");
const fileMeta = document.getElementById("file-meta");
const interpTitle = document.getElementById("interp-title");
const interpBody = document.getElementById("interp-body");
const exportPdfBtn = document.getElementById("export-pdf");

let report = null;
let desktopReady = false;

window.addEventListener("pywebviewready", () => {
  desktopReady = true;
});

uploadLabel.addEventListener("click", async (event) => {
  if (!desktopReady || !window.pywebview?.api?.pick_report_files) return;
  event.preventDefault();
  const picked = await window.pywebview.api.pick_report_files();
  if (!picked || picked.cancelled) return;
  if (picked.error) {
    applyReport(picked);
    return;
  }
  await interpretPicked(picked.files, picked.warning);
});

fileInput.addEventListener("change", async (event) => {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  const form = new FormData();
  Array.from(files).forEach((file) => form.append("files", file));
  setBusy(true);
  try {
    const response = await fetch("/interpret-reports", { method: "POST", body: form });
    const data = await response.json();
    if (!response.ok) {
      applyReport({ error: data.error || "Interpretation failed." });
      return;
    }
    applyReport(data);
  } catch (err) {
    applyReport({ error: err?.message || "Interpretation failed." });
  } finally {
    setBusy(false);
    fileInput.value = "";
  }
});

async function interpretPicked(files, warning) {
  setBusy(true);
  try {
    const response = await fetch("/interpret-reports", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ files }),
    });
    const data = await response.json();
    if (!response.ok) {
      applyReport({ error: data.error || "Interpretation failed." });
      return;
    }
    if (warning) data.warning = warning;
    applyReport(data);
  } catch (err) {
    applyReport({ error: err?.message || "Interpretation failed." });
  } finally {
    setBusy(false);
  }
}

exportPdfBtn.addEventListener("click", exportInterpretation);

async function exportInterpretation() {
  if (!report) return;
  exportPdfBtn.disabled = true;
  clearErrors();
  try {
    if (desktopReady && window.pywebview?.api?.export_interpretation) {
      const data = await window.pywebview.api.export_interpretation(report);
      if (!data || data.cancelled) return;
      if (data.error) showError(data.error);
      return;
    }

    const response = await fetch("/export-interpretation", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(report),
    });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      showError(data.error || "PDF export failed.");
      return;
    }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = downloadName(report);
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (err) {
    showError(err?.message || "PDF export failed.");
  } finally {
    exportPdfBtn.disabled = false;
  }
}

function setBusy(busy) {
  uploadLabel.classList.toggle("is-busy", busy);
  statusEl.hidden = !busy;
  if (busy) {
    emptyState.hidden = true;
    resultsEl.hidden = true;
    clearErrors();
  }
}

function applyReport(data) {
  if (!data || data.cancelled) {
    emptyState.hidden = false;
    resultsEl.hidden = true;
    return;
  }
  clearErrors();
  if (data.error) {
    showError(data.error);
    emptyState.hidden = false;
    resultsEl.hidden = true;
    report = null;
    return;
  }
  if (data.warning) showError(data.warning);

  report = data;
  emptyState.hidden = true;
  resultsEl.hidden = false;
  interpTitle.textContent = data.title || "Interpretation Report";
  const sources = Array.isArray(data.sources) ? data.sources.join(", ") : "";
  const model = data.model ? `Model ${data.model}` : "";
  fileMeta.textContent = [sources, model].filter(Boolean).join(" · ");
  interpBody.innerHTML = (data.sections || [])
    .map((section, index) => {
      const heading = escapeHtml(section.heading || "Note");
      const body = escapeHtml(section.body || "");
      return `
        <article class="interp-section">
          <p class="interp-kicker">${index + 1}</p>
          <div>
            <h3>${heading}</h3>
            <p>${body}</p>
          </div>
        </article>`;
    })
    .join("");
}

function downloadName(data) {
  const sources = Array.isArray(data.sources) ? data.sources : [];
  if (sources.length === 1) {
    const stem = String(sources[0] || "report").replace(/\.[^.]+$/, "");
    const safe = stem.replace(/[^\w.\-]+/g, "_").replace(/^[._]+|[._]+$/g, "") || "report";
    return `interpretation_${safe}.pdf`;
  }
  return "interpretation_report.pdf";
}

function clearErrors() {
  document.querySelectorAll(".error").forEach((node) => node.remove());
}

function showError(message) {
  const el = document.createElement("p");
  el.className = "error";
  el.textContent = message;
  document.querySelector(".topbar").after(el);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
