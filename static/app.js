const fileInput = document.getElementById("file-input");
const fileNav = document.getElementById("file-nav");
const emptyState = document.getElementById("empty-state");
const resultsEl = document.getElementById("results");
const statsEl = document.getElementById("stats");
const fileMeta = document.getElementById("file-meta");
const othersCount = document.getElementById("others-count");
const othersList = document.getElementById("others-list");
const uploadLabel = document.querySelector(".upload");
const exportPdfBtn = document.getElementById("export-pdf");

let results = [];
let activeIndex = 0;
let desktopReady = false;

window.addEventListener("pywebviewready", () => {
  desktopReady = true;
});

uploadLabel.addEventListener("click", async (event) => {
  if (!desktopReady || !window.pywebview?.api) return;
  event.preventDefault();
  const data = await window.pywebview.api.pick_and_analyze();
  applyPayload(data);
});

fileInput.addEventListener("change", async (event) => {
  const files = event.target.files;
  if (!files || files.length === 0) return;

  const form = new FormData();
  Array.from(files).forEach((file) => form.append("files", file));

  const response = await fetch("/analyze", { method: "POST", body: form });
  const data = await response.json();
  if (!response.ok) {
    applyPayload({ error: data.error || "Analysis failed." });
    return;
  }
  applyPayload(data);
});

exportPdfBtn.addEventListener("click", exportActivePdf);

async function exportActivePdf() {
  if (!results.length) return;
  const result = results[activeIndex];
  exportPdfBtn.disabled = true;
  document.querySelectorAll(".error").forEach((node) => node.remove());

  try {
    if (desktopReady && window.pywebview?.api?.export_pdf) {
      const data = await window.pywebview.api.export_pdf(result);
      if (!data || data.cancelled) return;
      if (data.error) showError(data.error);
      return;
    }

    const response = await fetch("/export-pdf", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result),
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
    link.download = pdfName(result.filename);
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

function pdfName(csvName) {
  const stem = String(csvName || "report").replace(/\.[^.]+$/, "");
  const safe = stem.replace(/[^\w.\-]+/g, "_").replace(/^[._]+|[._]+$/g, "") || "report";
  return `${safe}.pdf`;
}

function applyPayload(data) {
  if (!data || data.cancelled) return;
  document.querySelectorAll(".error").forEach((node) => node.remove());

  if (data.error) {
    showError(data.error);
    return;
  }

  if (data.errors && data.errors.length) {
    data.errors.forEach((item) => {
      showError(`${item.filename}: ${item.error}`);
    });
  }

  if (!data.results || !data.results.length) return;
  results = data.results;
  activeIndex = 0;
  renderNav();
  renderActive();
}

function showError(message) {
  const el = document.createElement("p");
  el.className = "error";
  el.textContent = message;
  document.querySelector(".topbar").after(el);
}

function renderNav() {
  fileNav.innerHTML = "";
  if (!results.length) {
    fileNav.hidden = true;
    return;
  }
  fileNav.hidden = false;
  results.forEach((result, index) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = result.filename;
    button.className = index === activeIndex ? "active" : "";
    button.addEventListener("click", () => {
      activeIndex = index;
      renderNav();
      renderActive();
    });
    fileNav.appendChild(button);
  });
}

function pct(part, total) {
  if (!total) return "0%";
  return `${((part / total) * 100).toFixed(1)}%`;
}

function renderActive() {
  if (!results.length) {
    emptyState.hidden = false;
    resultsEl.hidden = true;
    return;
  }

  const result = results[activeIndex];
  emptyState.hidden = true;
  resultsEl.hidden = false;

  fileMeta.textContent = `${result.column_count} answer_round columns · ${result.row_count} rows · ${result.total} values`;

  const labels = [
    ["he", "He", result.counts.he],
    ["she", "She", result.counts.she],
    ["he_she", "He/She", result.counts.he_she || 0],
    ["reject", "Reject", result.counts.reject],
    ["other", "Other", result.counts.other],
  ];

  statsEl.innerHTML = labels
    .map(
      ([key, label, value]) => `
        <article class="stat ${key}">
          <span class="label">${label}</span>
          <span class="value">${value}</span>
          <span class="share">${pct(value, result.total)}</span>
        </article>`
    )
    .join("");

  othersCount.textContent = `${result.others.length} entries`;
  othersList.innerHTML = renderItems(
    result.others,
    "This file has no values other than he / she / reject / he/she."
  );
}

function renderItems(items, emptyText) {
  if (!items.length) {
    return `<p class="empty-others">${emptyText}</p>`;
  }
  return items
    .map((item) => {
      const display = item.value ? item.value : "(empty)";
      const emptyClass = item.value ? "" : " empty";
      return `
        <article class="other-item">
          <div class="col">${escapeHtml(item.column)}</div>
          <div class="row">row ${item.row}</div>
          <div class="val${emptyClass}">${escapeHtml(display)}</div>
        </article>`;
    })
    .join("");
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}
