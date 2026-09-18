from __future__ import annotations

import io
import os
import re
from datetime import date
from typing import Any

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    KeepTogether,
    LongTable,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

BLACK = HexColor("#111111")
GRAY = HexColor("#555555")
LINE = HexColor("#cccccc")
RULE = HexColor("#111111")
HEADER_BG = HexColor("#f3f3f3")
ROW_BG = HexColor("#fafafa")
FRAME_PADDING = 12  # SimpleDocTemplate frames use 6pt left + 6pt right
SPLIT_IN_ROW = 20

_FONT_REGULAR = "Times-Roman"
_FONT_BOLD = "Times-Bold"
_FONT_ITALIC = "Times-Italic"
_FONTS_READY = False

_FONT_SETS = [
    (
        "/System/Library/Fonts/Supplemental/Times New Roman.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/System/Library/Fonts/Supplemental/Times New Roman Italic.ttf",
    ),
    (
        r"C:\Windows\Fonts\times.ttf",
        r"C:\Windows\Fonts\timesbd.ttf",
        r"C:\Windows\Fonts\timesi.ttf",
    ),
    (
        "/System/Library/Fonts/Supplemental/Georgia.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/System/Library/Fonts/Supplemental/Georgia Italic.ttf",
    ),
    (
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    ),
]


def _register_fonts() -> None:
    global _FONT_REGULAR, _FONT_BOLD, _FONT_ITALIC, _FONTS_READY
    if _FONTS_READY:
        return
    for regular, bold, italic in _FONT_SETS:
        if not os.path.isfile(regular):
            continue
        try:
            pdfmetrics.registerFont(TTFont("ReportSerif", regular))
            _FONT_REGULAR = "ReportSerif"
            if os.path.isfile(bold):
                pdfmetrics.registerFont(TTFont("ReportSerif-Bold", bold))
                _FONT_BOLD = "ReportSerif-Bold"
            else:
                _FONT_BOLD = "ReportSerif"
            if os.path.isfile(italic):
                pdfmetrics.registerFont(TTFont("ReportSerif-Italic", italic))
                _FONT_ITALIC = "ReportSerif-Italic"
            else:
                _FONT_ITALIC = "ReportSerif"
            _FONTS_READY = True
            return
        except Exception:  # noqa: BLE001
            continue
    _FONTS_READY = True


def pdf_filename(csv_name: str) -> str:
    stem = os.path.splitext(str(csv_name or "report"))[0]
    safe = re.sub(r"[^\w.\-]+", "_", stem, flags=re.UNICODE).strip("._")
    return f"{safe or 'report'}.pdf"


def _xml(value: Any) -> str:
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _xml_flow(value: Any) -> str:
    text = _xml(value).replace("\n", "<br/>")
    def _break_token(match: re.Match[str]) -> str:
        token = match.group(0)
        return "\u200b".join(token[i : i + 20] for i in range(0, len(token), 20))
    return re.sub(r"[^\s]{24,}", _break_token, text)


def _pct(part: int, total: int) -> str:
    if not total:
        return "0.0%"
    return f"{(part / total) * 100:.1f}%"


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle(
            "title",
            fontName=_FONT_BOLD,
            fontSize=16,
            leading=20,
            textColor=BLACK,
            spaceBefore=2,
            spaceAfter=2,
        ),
        "intro": ParagraphStyle(
            "intro",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=14,
            textColor=BLACK,
            spaceBefore=8,
            spaceAfter=10,
        ),
        "heading": ParagraphStyle(
            "heading",
            fontName=_FONT_BOLD,
            fontSize=11,
            leading=15,
            textColor=BLACK,
            spaceBefore=14,
            spaceAfter=8,
        ),
        "body": ParagraphStyle(
            "body",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=14,
            textColor=BLACK,
            spaceAfter=8,
        ),
        "meta_label": ParagraphStyle(
            "meta_label",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=GRAY,
        ),
        "meta_value": ParagraphStyle(
            "meta_value",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=BLACK,
        ),
        "th": ParagraphStyle(
            "th",
            fontName=_FONT_BOLD,
            fontSize=9,
            leading=12,
            textColor=BLACK,
        ),
        "th_right": ParagraphStyle(
            "th_right",
            fontName=_FONT_BOLD,
            fontSize=9,
            leading=12,
            textColor=BLACK,
            alignment=TA_RIGHT,
        ),
        "td": ParagraphStyle(
            "td",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=BLACK,
        ),
        "td_right": ParagraphStyle(
            "td_right",
            fontName=_FONT_REGULAR,
            fontSize=10,
            leading=13,
            textColor=BLACK,
            alignment=TA_RIGHT,
        ),
        "td_bold": ParagraphStyle(
            "td_bold",
            fontName=_FONT_BOLD,
            fontSize=10,
            leading=13,
            textColor=BLACK,
        ),
        "td_bold_right": ParagraphStyle(
            "td_bold_right",
            fontName=_FONT_BOLD,
            fontSize=10,
            leading=13,
            textColor=BLACK,
            alignment=TA_RIGHT,
        ),
        "td_empty": ParagraphStyle(
            "td_empty",
            fontName=_FONT_ITALIC,
            fontSize=10,
            leading=13,
            textColor=GRAY,
        ),
    }


def _plain_table(
    data: list[list[Any]],
    col_widths: list[float],
    header: bool = True,
) -> Table:
    table = LongTable(
        data,
        colWidths=col_widths,
        repeatRows=1 if header else 0,
        hAlign="LEFT",
    )
    style = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("GRID", (0, 0), (-1, -1), 0.4, LINE),
    ]
    if header:
        style.extend(
            [
                ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 0), (-1, 0), 6),
            ]
        )
    for row in range(1, len(data)):
        if row % 2 == 0:
            style.append(("BACKGROUND", (0, row), (-1, row), ROW_BG))
    table.setStyle(TableStyle(style))
    return table


def _others_header(col_widths: list[float], styles: dict[str, ParagraphStyle]) -> Table:
    table = Table(
        [
            [
                [Paragraph("No.", styles["th"])],
                [Paragraph("Column", styles["th"])],
                [Paragraph("Row", styles["th"])],
                [Paragraph("Value", styles["th"])],
            ]
        ],
        colWidths=col_widths,
        hAlign="LEFT",
        spaceBefore=0,
        spaceAfter=0,
    )
    table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (-1, -1), HEADER_BG),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("LINEABOVE", (0, 0), (-1, 0), 0.4, LINE),
                ("LINEBELOW", (0, 0), (-1, 0), 0.4, LINE),
                ("LINEBEFORE", (0, 0), (0, 0), 0.4, LINE),
                ("LINEAFTER", (0, 0), (-1, 0), 0.4, LINE),
            ]
        )
    )
    return table


def _others_row(
    cells: list[Any],
    col_widths: list[float],
    shaded: bool,
) -> Table:
    table = Table(
        [cells],
        colWidths=col_widths,
        splitInRow=SPLIT_IN_ROW,
        hAlign="LEFT",
        spaceBefore=0,
        spaceAfter=0,
    )
    commands = [
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.4, LINE),
        ("LINEBEFORE", (0, 0), (0, 0), 0.4, LINE),
        ("LINEAFTER", (0, 0), (-1, 0), 0.4, LINE),
    ]
    if shaded:
        commands.append(("BACKGROUND", (0, 0), (-1, -1), ROW_BG))
    table.setStyle(TableStyle(commands))
    return table


def _draw_page(canvas, doc, filename: str) -> None:
    canvas.saveState()
    canvas.setStrokeColor(RULE)
    canvas.setLineWidth(0.6)
    canvas.line(doc.leftMargin, A4[1] - 12 * mm, A4[0] - doc.rightMargin, A4[1] - 12 * mm)
    canvas.line(doc.leftMargin, 14 * mm, A4[0] - doc.rightMargin, 14 * mm)
    canvas.setFillColor(GRAY)
    canvas.setFont(_FONT_REGULAR, 8)
    canvas.drawString(doc.leftMargin, A4[1] - 10 * mm, "Answer Round Analysis Report")
    canvas.drawRightString(A4[0] - doc.rightMargin, A4[1] - 10 * mm, filename)
    canvas.drawString(doc.leftMargin, 10 * mm, date.today().strftime("%d %B %Y"))
    canvas.drawRightString(A4[0] - doc.rightMargin, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_report_pdf(result: dict[str, Any]) -> bytes:
    if not isinstance(result, dict):
        raise ValueError("Report data is missing.")

    _register_fonts()
    styles = _styles()

    filename = str(result.get("filename") or "untitled.csv")
    counts = result.get("counts") or {}
    he = int(counts.get("he") or 0)
    she = int(counts.get("she") or 0)
    he_she = int(counts.get("he_she") or 0)
    reject = int(counts.get("reject") or 0)
    other = int(counts.get("other") or 0)
    total = int(result.get("total") or (he + she + he_she + reject + other))
    column_count = int(result.get("column_count") or 0)
    row_count = int(result.get("row_count") or 0)
    others = result.get("others") or []
    if not isinstance(others, list):
        others = []

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
        title=f"Answer Round Analysis Report — {filename}",
        author="Answer Round",
    )
    usable = A4[0] - doc.leftMargin - doc.rightMargin - FRAME_PADDING
    story: list[Any] = []

    story.append(Paragraph("Answer Round Analysis Report", styles["title"]))
    story.append(
        Paragraph(
            "This report counts answers in columns whose names begin with "
            "answer_round. Matching is case-insensitive. Recognized values "
            "are he, she, he/she, and reject.",
            styles["intro"],
        )
    )

    meta = Table(
        [
            [
                Paragraph("Source file", styles["meta_label"]),
                Paragraph(_xml(filename), styles["meta_value"]),
            ],
            [
                Paragraph("Date", styles["meta_label"]),
                Paragraph(date.today().strftime("%d %B %Y"), styles["meta_value"]),
            ],
            [
                Paragraph("Answer columns", styles["meta_label"]),
                Paragraph(str(column_count), styles["meta_value"]),
            ],
            [
                Paragraph("Rows", styles["meta_label"]),
                Paragraph(str(row_count), styles["meta_value"]),
            ],
            [
                Paragraph("Values counted", styles["meta_label"]),
                Paragraph(str(total), styles["meta_value"]),
            ],
        ],
        colWidths=[usable * 0.32, usable * 0.68],
    )
    meta.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("LINEBELOW", (0, 0), (-1, -2), 0.3, LINE),
                ("LINEBELOW", (0, -1), (-1, -1), 0.6, RULE),
                ("LINEABOVE", (0, 0), (-1, 0), 0.6, RULE),
            ]
        )
    )
    story.append(meta)

    categories = [
        ("He", he),
        ("She", she),
        ("He/She", he_she),
        ("Reject", reject),
        ("Other", other),
    ]
    summary_rows = [
        [
            Paragraph("Category", styles["th"]),
            Paragraph("Count", styles["th_right"]),
            Paragraph("Share", styles["th_right"]),
        ]
    ]
    for label, value in categories:
        summary_rows.append(
            [
                Paragraph(_xml(label), styles["td"]),
                Paragraph(str(value), styles["td_right"]),
                Paragraph(_pct(value, total), styles["td_right"]),
            ]
        )
    summary_rows.append(
        [
            Paragraph("Total", styles["td_bold"]),
            Paragraph(str(total), styles["td_bold_right"]),
            Paragraph("100.0%" if total else "0.0%", styles["td_bold_right"]),
        ]
    )
    col_cat, col_count, col_share = usable * 0.50, usable * 0.25, usable * 0.25
    summary = _plain_table(summary_rows, [col_cat, col_count, col_share])
    summary.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, -1), (-1, -1), HEADER_BG),
                ("LINEABOVE", (0, -1), (-1, -1), 0.6, RULE),
            ]
        )
    )
    story.append(
        KeepTogether(
            [
                Paragraph("1. Response counts", styles["heading"]),
                summary,
            ]
        )
    )

    story.append(
        Paragraph(
            "2. Values other than he, she, reject, and he/she",
            styles["heading"],
        )
    )
    if not others:
        story.append(
            Paragraph("No such values were recorded in this file.", styles["body"])
        )
    else:
        story.append(
            Paragraph(
                f"{len(others)} value{'s' if len(others) != 1 else ''} "
                "fell outside the recognized categories.",
                styles["body"],
            )
        )
        col_widths = [usable * 0.08, usable * 0.28, usable * 0.10, usable * 0.54]
        story.append(_others_header(col_widths, styles))
        data_index = 0
        for index, item in enumerate(others, start=1):
            if not isinstance(item, dict):
                continue
            raw_value = str(item.get("value") or "").strip()
            empty = not raw_value
            value_style = styles["td_empty"] if empty else styles["td"]
            story.append(
                _others_row(
                    [
                        [Paragraph(str(index), styles["td"])],
                        [Paragraph(_xml(item.get("column") or ""), styles["td"])],
                        [Paragraph(str(item.get("row", "")), styles["td"])],
                        [Paragraph(_xml_flow(raw_value or "(empty)"), value_style)],
                    ],
                    col_widths,
                    shaded=data_index % 2 == 1,
                )
            )
            data_index += 1

    def on_page(canvas, doc_obj) -> None:
        _draw_page(canvas, doc_obj, filename)

    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return buffer.getvalue()
