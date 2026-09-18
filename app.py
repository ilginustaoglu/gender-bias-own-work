from __future__ import annotations

import csv
import io
import os
import re
import socket
import threading
import time
import urllib.error
import urllib.request
from typing import Any

import webview
from flask import Flask, jsonify, render_template, request, send_file
from werkzeug.serving import make_server

from pdf_report import build_report_pdf, pdf_filename

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

CANONICAL = {"he", "she", "reject", "he_she"}
HE_SHE_VALUES = {"he/she", "she/he"}


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1", "cp1254"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _read_csv_bytes(raw: bytes) -> tuple[list[str], list[dict[str, str]]]:
    text = _decode(raw)
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise ValueError("CSV header row was not found.")
    columns = [name for name in reader.fieldnames if name is not None]
    rows = [{key: (row.get(key) or "") for key in columns} for row in reader]
    return columns, rows


def _normalize(value: Any) -> str:
    text = str(value).strip().lower().rstrip(".")
    text = re.sub(r"\s*/\s*", "/", text)
    if text in HE_SHE_VALUES:
        return "he_she"
    return text


def analyze_csv(columns: list[str], rows: list[dict[str, str]], filename: str) -> dict[str, Any]:
    answer_columns = [col for col in columns if str(col).startswith("answer_round")]
    counts = {"he": 0, "she": 0, "he_she": 0, "reject": 0, "other": 0}
    others: list[dict[str, Any]] = []

    for col in answer_columns:
        for row_idx, row in enumerate(rows, start=1):
            value = row.get(col, "")
            normalized = _normalize(value)
            if normalized in CANONICAL:
                counts[normalized] += 1
                continue
            counts["other"] += 1
            others.append(
                {
                    "column": str(col),
                    "row": row_idx,
                    "value": str(value).strip(),
                }
            )

    return {
        "filename": filename,
        "columns": answer_columns,
        "column_count": len(answer_columns),
        "row_count": len(rows),
        "counts": counts,
        "total": sum(counts.values()),
        "others": others,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/analyze")
def analyze():
    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": "No CSV file was uploaded."}), 400

    results = []
    errors = []
    for file in files:
        name = file.filename or "untitled.csv"
        if not name.lower().endswith(".csv"):
            errors.append({"filename": name, "error": "Only CSV files are accepted."})
            continue
        try:
            columns, rows = _read_csv_bytes(file.read())
            results.append(analyze_csv(columns, rows, name))
        except Exception as exc:  # noqa: BLE001
            errors.append({"filename": name, "error": str(exc)})

    if not results and errors:
        return jsonify({"error": "No files could be analyzed.", "details": errors}), 400

    return jsonify({"results": results, "errors": errors})


@app.post("/export-pdf")
def export_pdf():
    result = request.get_json(silent=True)
    if not isinstance(result, dict):
        return jsonify({"error": "No report data was provided."}), 400
    try:
        pdf_bytes = build_report_pdf(result)
    except Exception as exc:  # noqa: BLE001
        return jsonify({"error": str(exc)}), 400
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name=pdf_filename(str(result.get("filename") or "report")),
    )


def analyze_path(path: str) -> dict[str, Any]:
    with open(path, "rb") as handle:
        columns, rows = _read_csv_bytes(handle.read())
    return analyze_csv(columns, rows, os.path.basename(path))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_server(url: str, timeout: float = 5.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url)
            return
        except (urllib.error.URLError, OSError):
            time.sleep(0.05)
    raise RuntimeError("The application window could not be opened.")


class DesktopApi:
    def __init__(self) -> None:
        self.window: webview.Window | None = None

    def pick_and_analyze(self) -> dict[str, Any]:
        if self.window is None:
            return {"error": "The window is not ready."}
        paths = self.window.create_file_dialog(
            webview.FileDialog.OPEN,
            allow_multiple=True,
            file_types=("CSV files (*.csv)",),
        )
        if not paths:
            return {"results": [], "errors": [], "cancelled": True}

        results = []
        errors = []
        for path in paths:
            name = os.path.basename(path)
            if not name.lower().endswith(".csv"):
                errors.append({"filename": name, "error": "Only CSV files are accepted."})
                continue
            try:
                results.append(analyze_path(path))
            except Exception as exc:  # noqa: BLE001
                errors.append({"filename": name, "error": str(exc)})

        if not results and errors:
            return {"error": "No files could be analyzed.", "details": errors}
        return {"results": results, "errors": errors}

    def export_pdf(self, result: dict[str, Any]) -> dict[str, Any]:
        if self.window is None:
            return {"error": "The window is not ready."}
        if not isinstance(result, dict):
            return {"error": "No report data was provided."}

        suggested = pdf_filename(str(result.get("filename") or "report"))
        paths = self.window.create_file_dialog(
            webview.FileDialog.SAVE,
            save_filename=suggested,
            file_types=("PDF files (*.pdf)",),
        )
        if not paths:
            return {"cancelled": True}

        path = paths[0] if isinstance(paths, (list, tuple)) else paths
        if not str(path).lower().endswith(".pdf"):
            path = f"{path}.pdf"

        try:
            with open(path, "wb") as handle:
                handle.write(build_report_pdf(result))
        except Exception as exc:  # noqa: BLE001
            return {"error": str(exc)}
        return {"ok": True, "path": path}


def run_desktop() -> None:
    port = _free_port()
    server = make_server("127.0.0.1", port, app, threaded=True)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}"
    _wait_for_server(url)

    api = DesktopApi()
    window = webview.create_window(
        "Answer Round",
        url,
        js_api=api,
        width=1100,
        height=780,
        min_size=(760, 560),
        text_select=True,
    )
    api.window = window
    webview.start()
    server.shutdown()


if __name__ == "__main__":
    run_desktop()
