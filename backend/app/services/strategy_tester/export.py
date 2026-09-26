"""CSV / Excel export for completed strategy test runs."""

from __future__ import annotations

import csv
import io
import zipfile
from xml.sax.saxutils import escape

from .scan_service import result_payload


RESULT_COLUMNS = [
    "rank",
    "symbol",
    "company",
    "signal",
    "status",
    "entry_price",
    "exit_price",
    "rr",
    "return_pct",
    "rsi",
    "sma_20",
    "sma_50",
    "sma_200",
    "volume",
    "avg_volume",
    "filters_passed",
    "filters_failed",
    "primary_failure_reason",
]


def results_to_csv(rows) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=RESULT_COLUMNS, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        payload = result_payload(row)
        writer.writerow({key: payload.get(key) for key in RESULT_COLUMNS})
    return buffer.getvalue()


def filter_stats_to_csv(stats) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["filter_id", "label", "passed", "failed", "pass_pct", "fail_pct", "funnel_remaining"])
    writer.writeheader()
    for item in stats:
        writer.writerow(
            {
                "filter_id": item.filter_id,
                "label": item.label,
                "passed": item.passed,
                "failed": item.failed,
                "pass_pct": item.pass_pct,
                "fail_pct": item.fail_pct,
                "funnel_remaining": item.funnel_remaining,
            }
        )
    return buffer.getvalue()


def results_to_xlsx_bytes(rows, stats, summary: dict) -> bytes:
    """Minimal OOXML workbook — no third-party Excel library required."""
    result_rows = [RESULT_COLUMNS]
    for row in rows:
        payload = result_payload(row)
        result_rows.append([_cell(payload.get(key)) for key in RESULT_COLUMNS])
    filter_rows = [["filter_id", "label", "passed", "failed", "pass_pct", "fail_pct", "funnel_remaining"]]
    for item in stats:
        filter_rows.append(
            [
                item.filter_id,
                item.label,
                item.passed,
                item.failed,
                item.pass_pct,
                item.fail_pct,
                item.funnel_remaining,
            ]
        )
    summary_rows = [["metric", "value"]]
    for key, value in (summary or {}).items():
        if isinstance(value, (dict, list)):
            continue
        summary_rows.append([key, value])
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _CONTENT_TYPES)
        zf.writestr("_rels/.rels", _RELS)
        zf.writestr("xl/workbook.xml", _workbook(["Results", "FilterAnalytics", "Summary"]))
        zf.writestr("xl/_rels/workbook.xml.rels", _workbook_rels(3))
        zf.writestr("xl/worksheets/sheet1.xml", _sheet_xml(result_rows))
        zf.writestr("xl/worksheets/sheet2.xml", _sheet_xml(filter_rows))
        zf.writestr("xl/worksheets/sheet3.xml", _sheet_xml(summary_rows))
    return buf.getvalue()


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.6g}"
    return str(value)


def _sheet_xml(rows: list[list]) -> str:
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>',
    ]
    for r_idx, row in enumerate(rows, start=1):
        cells = []
        for c_idx, value in enumerate(row, start=1):
            ref = f"{_col(c_idx)}{r_idx}"
            text = escape(str(value if value is not None else ""))
            if _is_number(value):
                cells.append(f'<c r="{ref}"><v>{text}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>')
        lines.append(f'<row r="{r_idx}">{"".join(cells)}</row>')
    lines.append("</sheetData></worksheet>")
    return "".join(lines)


def _is_number(value) -> bool:
    if isinstance(value, bool) or value is None or value == "":
        return False
    if isinstance(value, (int, float)):
        return True
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def _col(index: int) -> str:
    n = index
    out = ""
    while n:
        n, rem = divmod(n - 1, 26)
        out = chr(65 + rem) + out
    return out


def _workbook(names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, name in enumerate(names, start=1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets></workbook>"
    )


def _workbook_rels(count: int) -> str:
    rels = "".join(
        f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        for i in range(1, count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{rels}</Relationships>"
    )


_CONTENT_TYPES = """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
  <Override PartName="/xl/worksheets/sheet3.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>
"""

_RELS = """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>
"""
