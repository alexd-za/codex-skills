#!/usr/bin/env python3
"""Fusion CAD Guardian: evidence and deterministic mesh checks for Fusion MCP workflows."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from guardian_lib import VERSION
from guardian_lib.contracts import default_contract as _default_contract
from guardian_lib.contracts import validate_contract
from guardian_lib.core import GuardianError
from guardian_lib.core import analyze_mesh
from guardian_lib.core import cube_triangles as _cube_triangles
from guardian_lib.core import write_binary_stl as _write_binary_stl
from guardian_lib.evidence import default_evidence, populate_export_hashes, validate_evidence
from guardian_lib.reports import audit_stl, compare_reports, create_project, load_json
from guardian_lib.reports import render_audit_markdown, render_compare_markdown, render_gate_markdown
from guardian_lib.reports import run_gate, run_self_test, write_json, write_text


def _cmd_init(args: argparse.Namespace) -> int:
    output = Path(args.out)
    if output.exists() and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    write_json(output, _default_contract(args.part_name, args.task_type))
    print(f"Created contract template: {output}")
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    result = create_project(Path(args.directory), args.name, args.task_type)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_evidence_init(args: argparse.Namespace) -> int:
    contract = validate_contract(load_json(Path(args.contract)))
    output = Path(args.out)
    if output.exists() and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    write_json(output, default_evidence(contract))
    print(f"Created evidence ledger: {output}")
    return 0


def _cmd_evidence_hash(args: argparse.Namespace) -> int:
    path = Path(args.evidence)
    evidence = populate_export_hashes(load_json(path), path.resolve().parent)
    output = Path(args.out) if args.out else path
    write_json(output, evidence)
    print(json.dumps(evidence, indent=2, ensure_ascii=False))
    return 0


def _cmd_validate(args: argparse.Namespace) -> int:
    path = Path(args.file)
    data = load_json(path)
    if args.kind == "contract":
        validate_contract(data)
    else:
        validate_evidence(data)
    print(json.dumps({"valid": True, "kind": args.kind, "path": str(path.resolve())}, indent=2))
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    report = audit_stl(
        Path(args.mesh),
        contract_path=Path(args.contract) if args.contract else None,
        weld_tolerance_mm=args.weld_tolerance,
        area_epsilon_mm2=args.area_epsilon,
        sliver_quality_threshold=args.sliver_quality_threshold,
    )
    if args.json_out:
        write_json(Path(args.json_out), report)
    if args.markdown:
        write_text(Path(args.markdown), render_audit_markdown(report))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["verdict"] == "FAIL" else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    comparison = compare_reports(load_json(Path(args.before)), load_json(Path(args.after)))
    if args.json_out:
        write_json(Path(args.json_out), comparison)
    if args.markdown:
        write_text(Path(args.markdown), render_compare_markdown(comparison))
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
        mesh = Path(str(job["mesh"]))
        mesh = mesh if mesh.is_absolute() else base / mesh
        contract = Path(str(job["contract"])) if job.get("contract") else None
        if contract and not contract.is_absolute():
            contract = base / contract
        report = audit_stl(
            mesh,
            contract_path=contract,
            weld_tolerance_mm=args.weld_tolerance,
            area_epsilon_mm2=args.area_epsilon,
            sliver_quality_threshold=args.sliver_quality_threshold,
        )
        safe_name = "".join(char if char.isalnum() or char in "-_" else "_" for char in name)
        json_path = output_dir / f"{safe_name}.mesh-report.json"
        markdown_path = output_dir / f"{safe_name}.mesh-report.md"
        write_json(json_path, report)
        write_text(markdown_path, render_audit_markdown(report))
        summaries.append({
            "name": name,
            "mesh": str(mesh),
            "verdict": report["verdict"],
            "json_report": str(json_path),
            "markdown_report": str(markdown_path),
        })
        failed |= report["verdict"] == "FAIL"
    summary = {
        "guardian_version": VERSION,
        "manifest": str(manifest_path.resolve()),
        "jobs": summaries,
        "verdict": "FAIL" if failed else "PASS",
    }
    write_json(output_dir / "batch-summary.json", summary)
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    return 1 if failed else 0


def _cmd_gate(args: argparse.Namespace) -> int:
    report = run_gate(Path(args.contract), Path(args.evidence), [Path(item) for item in args.mesh_report])
    if args.json_out:
        write_json(Path(args.json_out), report)
    if args.markdown:
        write_text(Path(args.markdown), render_gate_markdown(report))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["overall_verdict"] in {"PASS", "CONDITIONAL_PASS"} else 1


def _cmd_self_test(_args: argparse.Namespace) -> int:
    result = run_self_test()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evidence and deterministic mesh verification for Autodesk Fusion MCP workflows"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a schema-v2 design contract")
    init.add_argument("--out", required=True)
    init.add_argument("--part-name", default="Example Part")
    init.add_argument("--task-type", choices=("part", "assembly"), default="part")
    init.add_argument("--force", action="store_true")
    init.set_defaults(func=_cmd_init)

    project = sub.add_parser("project", help="create a complete Guardian project workspace")
    project.add_argument("directory")
    project.add_argument("--name", required=True)
    project.add_argument("--task-type", choices=("part", "assembly"), default="part")
    project.set_defaults(func=_cmd_project)

    evidence_init = sub.add_parser("evidence-init", help="create an evidence ledger from a contract")
    evidence_init.add_argument("--contract", required=True)
    evidence_init.add_argument("--out", required=True)
    evidence_init.add_argument("--force", action="store_true")
    evidence_init.set_defaults(func=_cmd_evidence_init)

    evidence_hash = sub.add_parser("evidence-hash", help="populate export SHA-256 values in an evidence ledger")
    evidence_hash.add_argument("evidence")
    evidence_hash.add_argument("--out")
    evidence_hash.set_defaults(func=_cmd_evidence_hash)

    validate = sub.add_parser("validate", help="validate a Guardian JSON file")
    validate.add_argument("kind", choices=("contract", "evidence"))
    validate.add_argument("file")
    validate.set_defaults(func=_cmd_validate)

    audit = sub.add_parser("audit", help="audit an ASCII or binary STL")
    audit.add_argument("mesh")
    audit.add_argument("--contract")
    audit.add_argument("--json", dest="json_out")
    audit.add_argument("--markdown")
    audit.add_argument("--weld-tolerance", type=float, default=1e-6)
    audit.add_argument("--area-epsilon", type=float, default=1e-12)
    audit.add_argument("--sliver-quality-threshold", type=float, default=0.05)
    audit.set_defaults(func=_cmd_audit)

    compare = sub.add_parser("compare", help="compare two audit JSON reports")
    compare.add_argument("before")
    compare.add_argument("after")
    compare.add_argument("--json", dest="json_out")
    compare.add_argument("--markdown")
    compare.set_defaults(func=_cmd_compare)

    batch = sub.add_parser("batch", help="audit jobs from a batch manifest")
    batch.add_argument("manifest")
    batch.add_argument("--out-dir", required=True)
    batch.add_argument("--weld-tolerance", type=float, default=1e-6)
    batch.add_argument("--area-epsilon", type=float, default=1e-12)
    batch.add_argument("--sliver-quality-threshold", type=float, default=0.05)
    batch.set_defaults(func=_cmd_batch)

    acceptance = sub.add_parser("gate", help="combine Fusion evidence and mesh reports into an acceptance verdict")
    acceptance.add_argument("--contract", required=True)
    acceptance.add_argument("--evidence", required=True)
    acceptance.add_argument("--mesh-report", action="append", required=True)
    acceptance.add_argument("--json", dest="json_out")
    acceptance.add_argument("--markdown")
    acceptance.set_defaults(func=_cmd_gate)

    self_test = sub.add_parser("self-test", help="run built-in validation tests")
    self_test.set_defaults(func=_cmd_self_test)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except GuardianError as exc:
        print(f"guardian error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("guardian error: interrupted", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"guardian internal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
