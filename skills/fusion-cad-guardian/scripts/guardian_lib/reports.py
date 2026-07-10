from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import tempfile
from typing import Any

from . import VERSION
from .contracts import default_contract, evaluate_contract, mesh_contract, validate_contract
from .core import GuardianError, analyze_mesh, cube_triangles, read_stl, sha256_file, write_binary_stl
from .evidence import default_evidence, gate

LIMITATIONS = [
    "STL analysis does not verify assembly joints, motion, interference, or component connectivity.",
    "STL analysis does not verify minimum wall thickness, structural strength, material suitability, or print shrinkage.",
    "Bounding-box dimensions do not verify internal hole positions, local clearances, or feature tolerances.",
    "Downward-facing area is an orientation heuristic, not a slicer support simulation.",
    "Results depend on the STL matching the intended final Fusion body or component.",
]


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise GuardianError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GuardianError(f"invalid JSON in {path}: {exc}") from exc


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def audit_stl(
    mesh_path: Path,
    *,
    contract_path: Path | None = None,
    weld_tolerance_mm: float = 1e-6,
    area_epsilon_mm2: float = 1e-12,
    sliver_quality_threshold: float = 0.05,
) -> dict[str, Any]:
    stl_format, triangles = read_stl(mesh_path)
    contract = validate_contract(load_json(contract_path)) if contract_path else None
    mesh_rules = mesh_contract(contract) if contract else {}
    orientation = mesh_rules.get("orientation", {})
    metrics = analyze_mesh(
        triangles,
        weld_tolerance_mm=weld_tolerance_mm,
        area_epsilon_mm2=area_epsilon_mm2,
        sliver_quality_threshold=sliver_quality_threshold,
        build_axis=orientation.get("build_axis", "z"),
        severe_overhang_angle_degrees=float(orientation.get("severe_overhang_angle_degrees", 45.0)),
    )
    checks = evaluate_contract(metrics, contract, triangles) if contract else []
    verdict = "FAIL" if any(check["status"] == "FAIL" for check in checks) else "PASS"
    if contract is None:
        verdict = "AUDIT_ONLY"
    return {
        "guardian_version": VERSION,
        "generated_at": utc_now(),
        "mesh": {
            "path": str(mesh_path.resolve()),
            "sha256": sha256_file(mesh_path),
            "format": stl_format,
            "size_bytes": mesh_path.stat().st_size,
        },
        "contract": {
            "path": str(contract_path.resolve()) if contract_path else None,
            "sha256": sha256_file(contract_path) if contract_path else None,
            "schema_version": contract.get("schema_version") if contract else None,
            "part_name": contract.get("part_name") if contract else None,
        },
        "metrics": metrics,
        "checks": checks,
        "verdict": verdict,
        "limitations": LIMITATIONS,
    }


def render_audit_markdown(report: dict[str, Any]) -> str:
    metrics = report["metrics"]
    center = metrics.get("center_of_mass_mm")
    center_text = "Not available" if center is None else f"{center['x']:.6g}, {center['y']:.6g}, {center['z']:.6g} mm"
    lines = [
        "# Fusion CAD Guardian Mesh Report", "",
        f"- **Verdict:** {report['verdict']}",
        f"- **Mesh:** `{report['mesh']['path']}`",
        f"- **SHA-256:** `{report['mesh']['sha256']}`",
        f"- **Format:** {report['mesh']['format']}", "",
        "## Metrics", "",
        "| Metric | Value |", "|---|---:|",
        f"| Dimensions X × Y × Z | {metrics['dimensions_mm']['x']:.6g} × {metrics['dimensions_mm']['y']:.6g} × {metrics['dimensions_mm']['z']:.6g} mm |",
        f"| Triangles | {metrics['triangle_count']} |",
        f"| Unique vertices | {metrics['unique_vertex_count']} |",
        f"| Shells | {metrics['shell_count']} |",
        f"| Boundary edges | {metrics['boundary_edge_count']} |",
        f"| Non-manifold edges | {metrics['nonmanifold_edge_count']} |",
        f"| Degenerate triangles | {metrics['degenerate_triangle_count']} |",
        f"| Duplicate triangles | {metrics['duplicate_triangle_count']} |",
        f"| Inconsistent winding edges | {metrics['inconsistent_winding_edge_count']} |",
        f"| Sliver triangles | {metrics['sliver_triangle_count']} |",
        f"| Minimum triangle quality | {metrics['triangle_quality']['minimum']:.6g} |",
        f"| Surface area | {metrics['surface_area_mm2']:.6g} mm² |",
        f"| Absolute volume | {metrics['absolute_volume_mm3']:.6g} mm³ |",
        f"| Uniform-density centre of mass | {center_text} |",
        f"| Severe downward-facing area | {metrics['severe_downward_area']['area_mm2']:.6g} mm² |",
        f"| Watertight | {metrics['watertight']} |", "",
    ]
    if report["checks"]:
        lines += ["## Contract checks", "", "| Check | Status | Actual | Expected |", "|---|---|---:|---|"]
        for check in report["checks"]:
            lines.append(f"| `{check['id']}` | {check['status']} | {check['actual']} | {check['expected']} |")
        lines.append("")
    lines += ["## Limitations", ""] + [f"- {item}" for item in report["limitations"]]
    return "\n".join(lines) + "\n"


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    before_metrics, after_metrics = before["metrics"], after["metrics"]
    tracked = [
        "boundary_edge_count", "nonmanifold_edge_count", "degenerate_triangle_count",
        "duplicate_triangle_count", "inconsistent_winding_edge_count", "sliver_triangle_count",
        "shell_count", "triangle_count", "absolute_volume_mm3", "surface_area_mm2",
    ]
    deltas = {key: after_metrics[key] - before_metrics[key] for key in tracked}
    regressions: list[str] = []
    for key in tracked[:7]:
        if after_metrics[key] > before_metrics[key]:
            regressions.append(f"{key} increased from {before_metrics[key]} to {after_metrics[key]}")
    before_verdict, after_verdict = before.get("verdict"), after.get("verdict")
    if before_verdict == "PASS" and after_verdict == "FAIL":
        regressions.append("contract verdict changed from PASS to FAIL")
    return {
        "guardian_version": VERSION,
        "generated_at": utc_now(),
        "before": before.get("mesh"), "after": after.get("mesh"),
        "before_verdict": before_verdict, "after_verdict": after_verdict,
        "metric_deltas": deltas, "regressions": regressions,
        "comparison_verdict": "REGRESSION" if regressions else "NO_REGRESSION_DETECTED",
    }


def render_compare_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Fusion CAD Guardian Regression Report", "",
        f"- **Verdict:** {comparison['comparison_verdict']}",
        f"- **Before:** `{comparison['before']['path']}`",
        f"- **After:** `{comparison['after']['path']}`", "",
        "## Metric deltas", "", "| Metric | Delta |", "|---|---:|",
    ]
    lines += [f"| `{key}` | {value:+.6g} |" for key, value in comparison["metric_deltas"].items()]
    lines += ["", "## Regressions", ""]
    lines += [f"- {item}" for item in comparison["regressions"]] or ["- None detected by the configured comparison rules."]
    return "\n".join(lines) + "\n"


def render_gate_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Fusion CAD Guardian Acceptance Gate", "",
        f"- **Overall verdict:** {report['overall_verdict']}",
        f"- **Evidence verdict:** {report['evidence']['verdict']}",
        f"- **Export provenance:** {report['export_provenance']['verdict']}", "",
        "## Semantic and engineering evidence", "",
        "| Check | Required | Status | Method | Evidence |", "|---|---|---|---|---|",
    ]
    for item in report["evidence"]["checks"]:
        lines.append(
            f"| `{item['id']}` | {item['required']} | {item['status']} | {item.get('method', '')} | {item.get('evidence', item.get('reason', ''))} |"
        )
    lines += ["", "## Mesh reports", "", "| Mesh | Verdict | SHA-256 |", "|---|---|---|"]
    for item in report["mesh_reports"]:
        lines.append(f"| `{item['path']}` | {item['verdict']} | `{item['sha256']}` |")
    lines += ["", "## Open items", ""]
    open_items = (
        report["evidence"]["required_failures"]
        + report["evidence"]["required_not_verified"]
        + report["evidence"]["optional_open_items"]
    )
    lines += [f"- `{item}`" for item in open_items] or ["- None"]
    return "\n".join(lines) + "\n"


def create_project(directory: Path, name: str, task_type: str) -> dict[str, Any]:
    if directory.exists() and any(directory.iterdir()):
        raise GuardianError(f"project directory is not empty: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    for child in ("exports", "reports", "snapshots"):
        (directory / child).mkdir(exist_ok=True)
    contract = default_contract(name, task_type)
    evidence = default_evidence(contract)
    write_json(directory / "contract.json", contract)
    write_json(directory / "evidence.json", evidence)
    write_json(directory / "batch.json", {"jobs": []})
    task = f"""# {name}\n\nUse Fusion MCP for all live CAD operations. Use Fusion CAD Guardian for contracts, exported-mesh checks, evidence tracking, and the final acceptance gate.\n\n## Required sequence\n\n1. Inspect the connected Fusion MCP tools.\n2. Preserve the original design with a checkpoint.\n3. Replace placeholder criteria in `contract.json`.\n4. Build and inspect the design through Fusion MCP.\n5. Populate `evidence.json` with actual methods and evidence.\n6. Export final candidate meshes into `exports/`.\n7. Run mesh audits into `reports/`.\n8. Run the acceptance gate.\n9. Report unverified engineering assumptions explicitly.\n"""
    write_text(directory / "TASK.md", task)
    return {
        "guardian_version": VERSION,
        "directory": str(directory.resolve()),
        "contract": str((directory / "contract.json").resolve()),
        "evidence": str((directory / "evidence.json").resolve()),
        "task": str((directory / "TASK.md").resolve()),
    }


def run_gate(contract_path: Path, evidence_path: Path, mesh_report_paths: list[Path]) -> dict[str, Any]:
    contract = validate_contract(load_json(contract_path))
    evidence = load_json(evidence_path)
    mesh_reports = [load_json(path) for path in mesh_report_paths]
    result = gate(
        contract, evidence, mesh_reports, expected_contract_sha256=sha256_file(contract_path)
    )
    return {
        "guardian_version": VERSION,
        "generated_at": utc_now(),
        "contract": str(contract_path.resolve()),
        "evidence_ledger": str(evidence_path.resolve()),
        **result,
    }


def run_self_test() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="fusion-guardian-") as directory:
        root = Path(directory)
        cube_path = root / "cube.stl"
        write_binary_stl(cube_path, cube_triangles(10.0))
        cube_report = audit_stl(cube_path)
        metrics = cube_report["metrics"]
        center = metrics["center_of_mass_mm"]
        results.append({
            "name": "closed_cube",
            "passed": metrics["triangle_count"] == 12 and metrics["watertight"] and metrics["shell_count"] == 1
            and abs(metrics["absolute_volume_mm3"] - 1000.0) < 1e-6
            and center is not None and abs(center["x"] - 5.0) < 1e-6,
            "metrics": metrics,
        })
        open_path = root / "open.stl"
        write_binary_stl(open_path, [((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))])
        opened = audit_stl(open_path)["metrics"]
        results.append({"name": "open_triangle", "passed": opened["boundary_edge_count"] == 3 and not opened["watertight"], "metrics": opened})
        contract_path = root / "contract.json"
        contract = default_contract("Self-test cube")
        contract["mesh"]["expected_dimensions_mm"] = {axis: {"target": 10.0, "tolerance": 0.001} for axis in "xyz"}
        contract["mesh"]["max_sliver_triangles"] = 12
        write_json(contract_path, contract)
        contract_report = audit_stl(cube_path, contract_path=contract_path)
        results.append({"name": "contract_pass", "passed": contract_report["verdict"] == "PASS", "verdict": contract_report["verdict"]})
        project_dir = root / "project"
        project = create_project(project_dir, "Test Part", "part")
        results.append({"name": "project_scaffold", "passed": Path(project["contract"]).is_file() and Path(project["evidence"]).is_file()})
    return {"guardian_version": VERSION, "generated_at": utc_now(), "passed": all(item["passed"] for item in results), "tests": results}
