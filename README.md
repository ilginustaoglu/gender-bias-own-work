# Answer Round

A small desktop app that counts `answer_round` answers in CSV files. You can upload multiple files; each file is shown separately.

Only columns whose names start with `answer_round` are analyzed.

## What it counts

| Value | Matched as |
| --- | --- |
| **He** | `he`, `he.` |
| **She** | `she`, `she.` |
| **He/She** | `he/she`, `she/he`, including spaced or dotted variants |
| **Reject** | `reject` |
| **Other** | anything that is none of the above |

Matching is case-insensitive. Values other than he, she, reject, and he/she are listed one by one at the bottom of the report, with column, row, and the written text.

## Run

Python 3 is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

The app opens in its own window. Use **Upload CSV** to choose files, then switch between them with the tabs at the top.

To quit, close the window or press `Ctrl+C` in the terminal.
