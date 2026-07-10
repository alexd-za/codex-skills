from __future__ import annotations

from html import escape
import json
from typing import Any


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root {{ color-scheme: light dark; font-family: system-ui, sans-serif; }}
body {{ max-width: 1100px; margin: 2rem auto; padding: 0 1rem; line-height: 1.45; }}
h1,h2 {{ line-height: 1.15; }}
table {{ width: 100%; border-collapse: collapse; margin: 1rem 0 2rem; }}
th,td {{ border: 1px solid #8886; padding: .45rem .6rem; text-align: left; vertical-align: top; }}
th {{ background: #8882; }}
code,pre {{ font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }}
pre {{ padding: 1rem; overflow: auto; background: #8881; border: 1px solid #8884; }}
.pass {{ color: #188038; font-weight: 700; }} .fail {{ color: #c5221f; font-weight: 700; }}
.warn {{ color: #b06000; font-weight: 700; }} .muted {{ opacity: .72; }}
.small {{ font-size: .9rem; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def _status(value: Any) -> str:
    text = str(value)
    css = "pass" if text in {"PASS", "NO_REGRESSION_DETECTED"} else "fail" if text in {"FAIL", "REGRESSION"} else "warn"
    return f'<span class="{css}">{escape(text)}</span>'


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    head = "".join(f"<th>{escape(item)}</th>" for item in headers)
    body = "".join(
        "<tr>" + "".join(f"<td>{item if isinstance(item, str) and item.startswith('<span') else escape(str(item))}</td>" for item in row) + "</tr>"
        for row in rows
    )
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_audit_html(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    dimensions = metrics["dimensions_mm"]
    rows = [
        ["Dimensions X × Y × Z", f"{dimensions['x']:.6g} × {dimensions['y']:.6g} × {dimensions['z']:.6g} mm"],
        ["Triangles", metrics["triangle_count"]],
        ["Shells", metrics["shell_count"]],
        ["Boundary edges", metrics["boundary_edge_count"]],
        ["Non-manifold edges", metrics["nonmanifold_edge_count"]],
        ["Degenerate triangles", metrics["degenerate_triangle_count"]],
        ["Duplicate triangles", metrics["duplicate_triangle_count"]],
        ["Sliver triangles", metrics["sliver_triangle_count"]],
        ["Surface area", f"{metrics['surface_area_mm2']:.6g} mm²"],
        ["Absolute volume", f"{metrics['absolute_volume_mm3']:.6g} mm³"],
        ["Watertight", metrics["watertight"]],
    ]
    checks = _table(
        ["Check", "Status", "Actual", "Expected"],
        [[item["id"], _status(item["status"]), item["actual"], item["expected"]] for item in report.get("checks", [])],
    ) if report.get("checks") else "<p class='muted'>No contract checks were supplied.</p>"
    limitations = "".join(f"<li>{escape(item)}</li>" for item in report.get("limitations", []))
    body = f"""
<h1>Fusion CAD Guardian Mesh Report</h1>
<p><strong>Verdict:</strong> {_status(report['verdict'])}</p>
<p><strong>Input:</strong> <code>{escape(report['mesh']['path'])}</code><br>
<strong>SHA-256:</strong> <code>{escape(report['mesh']['sha256'])}</code><br>
<strong>Format:</strong> {escape(str(report['mesh']['format']))}</p>
<h2>Metrics</h2>{_table(['Metric', 'Value'], rows)}
<h2>Contract checks</h2>{checks}
<h2>Input preflight</h2><pre>{escape(json.dumps(report.get('input_preflight', {}), indent=2))}</pre>
<h2>Limitations</h2><ul>{limitations}</ul>
"""
    return _page("Fusion CAD Guardian Mesh Report", body)


def render_slicer_html(report: dict[str, Any]) -> str:
    metadata_rows = [[key, value] for key, value in report.get("metadata", {}).items()]
    checks = _table(
        ["Check", "Status", "Actual", "Expected"],
        [[item["id"], _status(item["status"]), item["actual"], item["expected"]] for item in report.get("checks", [])],
    ) if report.get("checks") else "<p class='muted'>Evidence-only report; no slicer contract checks were configured.</p>"
    body = f"""
<h1>Fusion CAD Guardian Slicer Evidence</h1>
<p><strong>Verdict:</strong> {_status(report['verdict'])}</p>
<p><strong>G-code:</strong> <code>{escape(report['gcode']['path'])}</code><br>
<strong>SHA-256:</strong> <code>{escape(report['gcode']['sha256'])}</code></p>
<h2>Detected metadata</h2>{_table(['Field', 'Value'], metadata_rows)}
<h2>Checks</h2>{checks}
<h2>Preflight</h2><pre>{escape(json.dumps(report.get('preflight', {}), indent=2))}</pre>
"""
    return _page("Fusion CAD Guardian Slicer Evidence", body)


def render_compare_html(report: dict[str, Any]) -> str:
    rows = [[key, f"{value:+.6g}"] for key, value in report["metric_deltas"].items()]
    regressions = "".join(f"<li>{escape(item)}</li>" for item in report.get("regressions", [])) or "<li>None detected.</li>"
    body = f"""
<h1>Fusion CAD Guardian Regression Report</h1>
<p><strong>Verdict:</strong> {_status(report['comparison_verdict'])}</p>
<h2>Metric deltas</h2>{_table(['Metric', 'Delta'], rows)}
<h2>Regressions</h2><ul>{regressions}</ul>
"""
    return _page("Fusion CAD Guardian Regression Report", body)


def render_gate_html(report: dict[str, Any]) -> str:
    evidence_rows = [
        [item["id"], item.get("part_id") or "", item["required"], _status(item["status"]), item.get("method", ""), item.get("evidence", item.get("reason", ""))]
        for item in report["evidence"]["checks"]
    ]
    mesh_rows = [[item.get("part_id") or "", item["path"], _status(item["verdict"]), _status(item["status"]), item["sha256"]] for item in report.get("mesh_reports", [])]
    slicer_rows = [[item.get("part_id") or "", item["path"], _status(item["verdict"]), _status(item["status"]), item["sha256"]] for item in report.get("slicer_reports", [])]
    open_items = report["evidence"]["required_failures"] + report["evidence"]["required_not_verified"] + report["evidence"]["optional_open_items"]
    open_html = "".join(f"<li><code>{escape(item)}</code></li>" for item in open_items) or "<li>None</li>"
    body = f"""
<h1>Fusion CAD Guardian Acceptance Gate</h1>
<p><strong>Overall verdict:</strong> {_status(report['overall_verdict'])}<br>
<strong>Evidence:</strong> {_status(report['evidence']['verdict'])}<br>
<strong>Export provenance:</strong> {_status(report['export_provenance']['verdict'])}</p>
<h2>Evidence</h2>{_table(['Check', 'Part', 'Required', 'Status', 'Method', 'Evidence'], evidence_rows)}
<h2>Mesh reports</h2>{_table(['Part', 'Report', 'Verdict', 'Status', 'SHA-256'], mesh_rows)}
<h2>Slicer reports</h2>{_table(['Part', 'Report', 'Verdict', 'Status', 'SHA-256'], slicer_rows) if slicer_rows else '<p class="muted">No slicer reports supplied.</p>'}
<h2>Open items</h2><ul>{open_html}</ul>
"""
    return _page("Fusion CAD Guardian Acceptance Gate", body)
