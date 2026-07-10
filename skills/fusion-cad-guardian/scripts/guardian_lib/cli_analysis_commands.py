"""Mesh, slicer, comparison, and batch CLI commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from . import VERSION
from .contracts import validate_contract
from .errors import GuardianError
from .html_report import render_audit_html, render_compare_html, render_slicer_html
from .meshio import inspect_3mf
from .reports import (
    audit_mesh, compare_reports, load_json, render_audit_markdown,
    render_compare_markdown, render_slicer_markdown, validate_audit_report,
    write_json, write_text,
)
from .slicer import build_slicer_report, validate_slicer_report
from .bundle import validate_bundle_manifest
from .capabilities import validate_capability_profile
from .evidence import validate_evidence
from .cli_project_commands import _resource_limits, _write_outputs


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = load_json(path)
    validators = {
        "contract": validate_contract,
        "evidence": validate_evidence,
        "capabilities": validate_capability_profile,
        "audit-report": validate_audit_report,
        "slicer-report": validate_slicer_report,
        "bundle-manifest": validate_bundle_manifest,
    }
    validators[args.kind](data)
    print(json.dumps({"valid": True, "kind": args.kind, "path": str(path.resolve())}, indent=2))
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    report = audit_mesh(
        Path(args.mesh),
        contract_path=Path(args.contract) if args.contract else None,
        part_id=args.part_id,
        object_id=args.object_id,
        object_name=args.object_name,
        weld_tolerance_mm=args.weld_tolerance,
        area_epsilon_mm2=args.area_epsilon,
        sliver_quality_threshold=args.sliver_quality_threshold,
        resource_limits=_resource_limits(args),
    )
    _write_outputs(report, args, render_audit_markdown, render_audit_html)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["verdict"] == "FAIL" else 0


def _cmd_inspect_3mf(args: argparse.Namespace) -> int:
    result = inspect_3mf(Path(args.mesh), limits=_resource_limits(args))
    if args.json_out:
        write_json(Path(args.json_out), result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_slicer_audit(args: argparse.Namespace) -> int:
    report = build_slicer_report(
        Path(args.gcode),
        source_mesh_path=Path(args.source_mesh) if args.source_mesh else None,
        part_id=args.part_id,
        contract_path=Path(args.contract) if args.contract else None,
        limits=_resource_limits(args),
    )
    _write_outputs(report, args, render_slicer_markdown, render_slicer_html)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["verdict"] == "FAIL" else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    comparison = compare_reports(load_json(Path(args.before)), load_json(Path(args.after)))
    _write_outputs(comparison, args, render_compare_markdown, render_compare_html)
    print(json.dumps(comparison, indent=2, ensure_ascii=False))
    return 1 if comparison["comparison_verdict"] == "REGRESSION" else 0


def _cmd_batch(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = load_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("jobs"), list):
        raise GuardianError("batch manifest must contain a jobs array")
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = manifest_path.resolve().parent
    summaries: list[dict[str, Any]] = []
    failed = False
    for index, job in enumerate(manifest["jobs"]):
        if not isinstance(job, dict) or "mesh" not in job:
            raise GuardianError(f"batch job {index} must contain mesh")
        name = str(job.get("name") or Path(str(job["mesh"])).stem)
        mesh = Path(str(job["mesh"])); mesh = mesh if mesh.is_absolute() else base / mesh
        contract = Path(str(job["contract"])) if job.get("contract") else None
        if contract and not contract.is_absolute(): contract = base / contract
        report = audit_mesh(
            mesh,
            contract_path=contract,
            part_id=job.get("part_id"),
            object_id=job.get("object_id"),
            object_name=job.get("object_name"),
            weld_tolerance_mm=args.weld_tolerance,
            area_epsilon_mm2=args.area_epsilon,
            sliver_quality_threshold=args.sliver_quality_threshold,
            resource_limits=_resource_limits(args),
        )
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
        json_path = output_dir / f"{safe_name}.mesh-report.json"
        markdown_path = output_dir / f"{safe_name}.mesh-report.md"
        html_path = output_dir / f"{safe_name}.mesh-report.html"
        write_json(json_path, report)
        write_text(markdown_path, render_audit_markdown(report))
        write_text(html_path, render_audit_html(report))
        summaries.append({
            "name": name, "part_id": report.get("contract", {}).get("part_id"),
            "mesh": str(mesh), "verdict": report["verdict"],
            "json_report": str(json_path), "markdown_report": str(markdown_path), "html_report": str(html_path),
        })
        failed |= report["verdict"] == "FAIL"
    summary = {"guardian_version": VERSION, "manifest": str(manifest_path.resolve()), "jobs": summaries, "verdict": "FAIL" if failed else "PASS"}
    write_json(output_dir / "batch-summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if failed else 0
