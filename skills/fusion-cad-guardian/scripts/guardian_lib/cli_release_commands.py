"""Acceptance, bundle, migration, diagnostic, and self-test CLI commands."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
from typing import Any

from . import VERSION
from .bundle import create_bundle, project_bundle_files, verify_bundle
from .capabilities import validate_capability_profile
from .contracts import CONTRACT_SCHEMA_URI, validate_contract
from .errors import GuardianError
from .evidence import validate_evidence
from .html_report import render_gate_html
from .limits import DEFAULT_RESOURCE_LIMITS
from .reports import load_json, render_gate_markdown, run_gate, run_self_test, write_json
from .cli_project_commands import SCRIPT_DIR, _resource_limits, _write_outputs


def _cmd_gate(args: argparse.Namespace) -> int:
    report = run_gate(
        Path(args.contract), Path(args.evidence),
        [Path(item) for item in args.mesh_report],
        [Path(item) for item in (args.slicer_report or [])],
    )
    _write_outputs(report, args, render_gate_markdown, render_gate_html)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["overall_verdict"] in {"PASS", "CONDITIONAL_PASS"} else 1


def _cmd_bundle(args: argparse.Namespace) -> int:
    project = Path(args.project)
    result = create_bundle(
        Path(args.out),
        project_bundle_files(project, include_exports=args.include_exports),
        metadata={"project": str(project.resolve()), "include_exports": args.include_exports},
        limits=_resource_limits(args),
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


def _cmd_bundle_verify(args: argparse.Namespace) -> int:
    result = verify_bundle(Path(args.bundle), limits=_resource_limits(args))
    if args.json_out:
        write_json(Path(args.json_out), result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


def _cmd_migrate(args: argparse.Namespace) -> int:
    path = Path(args.contract)
    contract = load_json(path)
    if not isinstance(contract, dict):
        raise GuardianError("contract must be a JSON object")
    if contract.get("schema_version", 1) == 1:
        raise GuardianError("automatic migration from schema_version 1 is intentionally unsupported; create a v2.2 contract and copy reviewed criteria")
    contract["$schema"] = CONTRACT_SCHEMA_URI
    contract["schema_revision"] = "2.2"
    contract.setdefault("slicer", {})
    for part in contract.get("parts", []):
        part.setdefault("slicer", {})
    limits = dict(DEFAULT_RESOURCE_LIMITS.to_dict())
    limits.update(contract.get("resource_limits", {}))
    contract["resource_limits"] = limits
    contract = validate_contract(contract)
    output = Path(args.out) if args.out else path
    if output.exists() and output != path and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    write_json(output, contract)
    print(json.dumps({"migrated": True, "path": str(output.resolve()), "schema_revision": "2.2"}, indent=2))
    return 0


def _cmd_doctor(args: argparse.Namespace) -> int:
    checks: list[dict[str, Any]] = []
    checks.append({"id": "python", "status": "PASS" if sys.version_info >= (3, 10) else "FAIL", "actual": platform.python_version(), "expected": ">= 3.10"})
    root = SCRIPT_DIR.parent.parent
    required = [root / "SKILL.md", root / "VERSION", root / "manifest.txt", root / "schemas" / "contract.schema.json"]
    for path in required:
        checks.append({"id": f"file:{path.name}", "status": "PASS" if path.is_file() else "FAIL", "actual": str(path), "expected": "present"})
    version_path = root / "VERSION"
    if version_path.is_file():
        version_text = version_path.read_text(encoding="utf-8").strip()
        checks.append({"id": "version_consistency", "status": "PASS" if version_text == VERSION else "FAIL", "actual": version_text, "expected": VERSION})
    manifest_path = root / "manifest.txt"
    if manifest_path.is_file():
        declared = {line.strip() for line in manifest_path.read_text(encoding="utf-8").splitlines() if line.strip()}
        actual = {
            str(path.relative_to(root)).replace("\\", "/")
            for path in root.rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        missing = sorted(declared - actual)
        unexpected = sorted(actual - declared)
        checks.append({
            "id": "manifest_integrity",
            "status": "PASS" if not missing and not unexpected else "FAIL",
            "actual": {"missing": missing, "unexpected": unexpected},
            "expected": "manifest exactly matches package files",
        })
    self_test = run_self_test()
    checks.append({"id": "self_test", "status": "PASS" if self_test["passed"] else "FAIL", "actual": self_test["passed"], "expected": True})
    if args.project:
        project = Path(args.project)
        validators = {
            "contract.json": validate_contract,
            "evidence.json": validate_evidence,
            "capabilities.json": validate_capability_profile,
        }
        for name, validator in validators.items():
            path = project / name
            try:
                validator(load_json(path))
                status, actual = "PASS", "valid"
            except GuardianError as exc:
                status, actual = "FAIL", str(exc)
            checks.append({"id": f"project:{name}", "status": status, "actual": actual, "expected": "valid"})
    result = {"guardian_version": VERSION, "passed": all(item["status"] == "PASS" for item in checks), "checks": checks}
    if args.json_out:
        write_json(Path(args.json_out), result)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


def _cmd_self_test(_args: argparse.Namespace) -> int:
    result = run_self_test()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1
