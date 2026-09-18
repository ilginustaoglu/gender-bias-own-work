from __future__ import annotations

import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
from typing import Any

OLLAMA_URL = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434").rstrip("/")
PREFERRED_MODELS = ("llama3.1", "llama3.1:latest", "llama3.1:8b")
MAX_FILE_CHARS = 8000
MAX_TOTAL_CHARS = 24000


def _request(path: str, payload: dict[str, Any] | None = None, timeout: float = 10.0) -> Any:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(f"{OLLAMA_URL}{path}", data=data, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def ollama_up() -> bool:
    try:
        urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=1.5)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def ensure_ollama(timeout: float = 12.0) -> None:
    if ollama_up():
        return
    try:
        subprocess.Popen(
            ["ollama", "serve"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("Ollama was not found on this computer.") from exc
    deadline = time.time() + timeout
    while time.time() < deadline:
        if ollama_up():
            return
        time.sleep(0.25)
    raise RuntimeError("Ollama is installed but not running. Open the Ollama app and try again.")


def resolve_model() -> str:
    ensure_ollama()
    payload = _request("/api/tags", timeout=8.0)
    names = [str(item.get("name") or "") for item in payload.get("models") or []]
    available = [name for name in names if name]
    for preferred in PREFERRED_MODELS:
        if preferred in available:
            return preferred
    for name in available:
        if name.startswith("llama3.1"):
            return name
    if available:
        raise RuntimeError(
            "Llama 3.1 was not found. Available models: " + ", ".join(available)
        )
    raise RuntimeError("No Ollama models were found. Pull llama3.1 and try again.")


def _clip(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    return text[: limit].rstrip() + "\n[truncated]"


def interpret_reports(files: list[dict[str, str]]) -> dict[str, Any]:
    if not files:
        raise ValueError("No reports were provided.")

    model = resolve_model()
    chunks: list[str] = []
    used = 0
    sources: list[str] = []
    for item in files:
        name = str(item.get("filename") or "report.pdf")
        body = _clip(str(item.get("text") or ""), MAX_FILE_CHARS)
        if not body.strip():
            continue
        sources.append(name)
        room = MAX_TOTAL_CHARS - used
        if room <= 0:
            break
        clipped = _clip(body, room)
        used += len(clipped)
        chunks.append(f"FILE: {name}\n{clipped}")

    if not chunks:
        raise ValueError("No readable text was found in the uploaded reports.")

    prompt = (
        "Write a short, tidy research note on the pronoun counts in the Answer Round reports.\n"
        "Use only numbers that appear in the reports. Do not invent data.\n"
        "If several files are given, treat each file as one model or batch and compare them.\n"
        "Comment on he, she, he/she, reject, and other.\n\n"
        "Reply with JSON only. No markdown, no asterisks, no TITLE or SECTION labels.\n"
        "Use this schema:\n"
        "{"
        '"title": "short plain title",'
        '"sections": ['
        '{"heading": "Overview", "body": "2-4 sentences"},'
        '{"heading": "Distribution", "body": "2-4 sentences"},'
        '{"heading": "Bias reading", "body": "2-4 sentences"},'
        '{"heading": "Other answers", "body": "2-4 sentences"},'
        '{"heading": "Conclusion", "body": "2-4 sentences"}'
        "]}\n\n"
        "Reports:\n\n" + "\n\n".join(chunks)
    )
    result = _request(
        "/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.2, "num_predict": 900},
        },
        timeout=180.0,
    )
    raw = str(result.get("response") or "").strip()
    if not raw:
        raise RuntimeError("Llama 3.1 returned an empty response.")
    parsed = parse_commentary(raw)
    parsed["sources"] = sources
    parsed["model"] = model
    parsed["raw"] = raw
    return parsed


def parse_commentary(raw: str) -> dict[str, Any]:
    text = str(raw or "").strip()
    parsed = _parse_json_commentary(text)
    if parsed is None:
        parsed = _parse_labeled_commentary(text)
    return _normalize_commentary(parsed, text)


def _parse_json_commentary(raw: str) -> dict[str, Any] | None:
    candidate = raw.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", candidate, re.S | re.I)
    if fenced:
        candidate = fenced.group(1)
    else:
        start = candidate.find("{")
        end = candidate.rfind("}")
        if start != -1 and end > start:
            candidate = candidate[start : end + 1]
    try:
        data = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    sections_in = data.get("sections")
    sections: list[dict[str, str]] = []
    if isinstance(sections_in, list):
        for item in sections_in:
            if not isinstance(item, dict):
                continue
            heading = _clean_heading(item.get("heading") or item.get("title") or "")
            body = _clean_body(item.get("body") or item.get("text") or "")
            if body:
                sections.append({"heading": heading or "Note", "body": body})
    title = _clean_heading(data.get("title") or "") or "Interpretation Report"
    if not sections:
        return None
    return {"title": title, "sections": sections}


KNOWN_HEADINGS = (
    "Overview",
    "Distribution",
    "Bias reading",
    "Other answers",
    "Conclusion",
)


def _split_heading_and_rest(text: str) -> tuple[str, str]:
    rest = " ".join(str(text or "").split()).strip()
    lowered = rest.lower()
    for name in sorted(KNOWN_HEADINGS, key=len, reverse=True):
        prefix = name.lower()
        if lowered == prefix:
            return name, ""
        if lowered.startswith(prefix) and (len(rest) == len(name) or not rest[len(name)].isalnum()):
            leftover = rest[len(name) :].strip(" :-")
            return name, leftover
    return _clean_heading(rest), ""


def _parse_labeled_commentary(raw: str) -> dict[str, Any]:
    text = raw.replace("\r\n", "\n")
    text = re.sub(r"\*{1,2}", "", text)
    text = re.sub(r"(?i)\bTITLE\s*:\s*", "\nTITLE: ", text)
    text = re.sub(r"(?i)\bSECTION\s*:\s*", "\nSECTION: ", text)
    text = re.sub(r"(?m)^#{1,3}\s+", "SECTION: ", text)

    title = "Interpretation Report"
    sections: list[dict[str, str]] = []
    current_heading = "Overview"
    current_lines: list[str] = []

    def flush() -> None:
        body = _clean_body(" ".join(current_lines))
        if body:
            sections.append({"heading": current_heading, "body": body})

    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.upper().startswith("TITLE:"):
            flush()
            current_heading = "Overview"
            current_lines = []
            heading, leftover = _split_heading_and_rest(stripped.split(":", 1)[1])
            title = heading or title
            if leftover:
                current_lines.append(leftover)
            continue
        if stripped.upper().startswith("SECTION:"):
            flush()
            heading, leftover = _split_heading_and_rest(stripped.split(":", 1)[1])
            current_heading = heading or "Note"
            current_lines = [leftover] if leftover else []
            continue
        current_lines.append(stripped)
    flush()
    if not sections:
        body = _clean_body(text)
        sections = [{"heading": "Overview", "body": body}] if body else []
    return {"title": title, "sections": sections}


def _clean_heading(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\*{1,2}", "", text)
    text = re.sub(r"(?i)^(title|section)\s*:\s*", "", text)
    text = re.sub(r"^#+\s*", "", text)
    return " ".join(text.split()).strip(" :-")


def _clean_body(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"\*{1,2}", "", text)
    text = re.sub(r"(?i)\b(title|section)\s*:\s*", "", text)
    return " ".join(text.split()).strip()


def _normalize_commentary(parsed: dict[str, Any], fallback: str) -> dict[str, Any]:
    title = _clean_heading(parsed.get("title") or "") or "Interpretation Report"
    preferred = ["Overview", "Distribution", "Bias reading", "Other answers", "Conclusion"]
    by_name: dict[str, str] = {}
    extras: list[dict[str, str]] = []
    for item in parsed.get("sections") or []:
        if not isinstance(item, dict):
            continue
        heading = _clean_heading(item.get("heading") or "") or "Note"
        body = _clean_body(item.get("body") or "")
        if not body:
            continue
        matched = next((name for name in preferred if name.lower() == heading.lower()), None)
        if matched:
            by_name[matched] = body
        else:
            extras.append({"heading": heading, "body": body})
    sections = [{"heading": name, "body": by_name[name]} for name in preferred if name in by_name]
    sections.extend(extras)
    if not sections:
        body = _clean_body(fallback)
        if body:
            sections = [{"heading": "Overview", "body": body}]
    return {"title": title, "sections": sections}
