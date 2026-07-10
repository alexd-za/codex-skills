#!/usr/bin/env python3
"""Command implementations for the Fusion CAD Guardian CLI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import sys
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from guardian_lib import VERSION
from guardian_lib.bundle import create_bundle, project_bundle_files, validate_bundle_manifest, verify_bundle
from guardian_lib.capabilities import (
    CAPABILITY_KEYS,
    build_verification_plan,
    default_capability_profile,
    set_capability,
    validate_capability_profile,
)
from guardian_lib.contracts import (
    CONTRACT_SCHEMA_URI,
    default_contract as _default_contract,
    default_part,
    validate_contract,
)
from guardian_lib.core import analyze_mesh
from guardian_lib.core import cube_triangles as _cube_triangles
from guardian_lib.core import write_binary_stl as _write_binary_stl
from guardian_lib.errors import GuardianError
from guardian_lib.evidence import default_evidence, populate_export_hashes, validate_evidence
from guardian_lib.html_report import render_audit_html, render_compare_html, render_gate_html, render_slicer_html
from guardian_lib.limits import DEFAULT_RESOURCE_LIMITS, ResourceLimits
from guardian_lib.meshio import inspect_3mf
from guardian_lib.reports import (
    audit_mesh,
    audit_stl,
    compare_reports,
    create_project,
    load_json,
    render_audit_markdown,
    render_compare_markdown,
    render_gate_markdown,
    render_slicer_markdown,
    run_gate,
    run_self_test,
    validate_audit_report,
    write_json,
    write_text,
)
from guardian_lib.slicer import build_slicer_report, validate_slicer_report


def _parse_part(value: str) -> tuple[str, str]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("part must use ID=Display Name")
    part_id, name = value.split("=", 1)
    if not part_id.strip() or not name.strip():
        raise argparse.ArgumentTypeError("part must use non-empty ID=Display Name")
    return part_id.strip(), name.strip()


def _resource_limits(args: argparse.Namespace) -> ResourceLimits:
    return ResourceLimits(
        max_file_size_mb=args.max_file_size_mb,
        max_triangles=args.max_input_triangles,
        max_coordinate_abs_mm=args.max_coordinate_abs_mm,
        max_estimated_memory_mb=args.max_estimated_memory_mb,
        max_archive_entries=args.max_archive_entries,
        max_archive_uncompressed_mb=args.max_archive_uncompressed_mb,
        max_compression_ratio=args.max_compression_ratio,
    ).validate()


def _write_outputs(data: dict[str, Any], args: argparse.Namespace, markdown_renderer=None, html_renderer=None) -> None:
    if getattr(args, "json_out", None):
        write_json(Path(args.json_out), data)
    if getattr(args, "markdown", None) and markdown_renderer:
        write_text(Path(args.markdown), markdown_renderer(data))
    if getattr(args, "html", None) and html_renderer:
        write_text(Path(args.html), html_renderer(data))


def _cmd_init(args: argparse.Namespace) -> int:
    output = Path(args.out)
    if output.exists() and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    write_json(output, _default_contract(args.part_name, args.task_type, parts=args.part or None))
    print(f"Created contract template: {output}")
    return 0


def _cmd_part_add(args: argparse.Namespace) -> int:
    source = Path(args.contract)
    contract = validate_contract(load_json(source))
    if contract.get("schema_version") != 2:
        raise GuardianError("part-add requires a schema-version 2 contract")
    if contract.get("mesh"):
        contract["mesh"] = {}
        contract["slicer"] = {}
    if any(part["id"] == args.id for part in contract.get("parts", [])):
        raise GuardianError(f"part id already exists: {args.id}")
    contract.setdefault("parts", []).append(default_part(args.id, args.name))
    contract = validate_contract(contract)
    output = Path(args.out) if args.out else source
    if output.exists() and output != source and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    write_json(output, contract)
    print(f"Added part {args.id}: {args.name} to {output}")
    return 0


def _cmd_project(args: argparse.Namespace) -> int:
    result = create_project(Path(args.directory), args.name, args.task_type, parts=args.part or None)
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


def _cmd_capabilities_init(args: argparse.Namespace) -> int:
    output = Path(args.out)
    if output.exists() and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    write_json(output, default_capability_profile(args.server_name))
    print(f"Created capability profile: {output}")
    return 0


def _cmd_capabilities_set(args: argparse.Namespace) -> int:
    path = Path(args.profile)
    profile = set_capability(
        load_json(path), args.capability, args.status,
        tool=args.tool or "", method=args.method or "", notes=args.notes or "",
    )
    output = Path(args.out) if args.out else path
    write_json(output, profile)
    print(json.dumps(profile["capabilities"][args.capability], indent=2, ensure_ascii=False))
    return 0


def _cmd_plan(args: argparse.Namespace) -> int:
    contract = validate_contract(load_json(Path(args.contract)))
    profile = validate_capability_profile(load_json(Path(args.capabilities)))
    plan = build_verification_plan(contract, profile)
    if args.json_out:
        write_json(Path(args.json_out), plan)
    print(json.dumps(plan, indent=2, ensure_ascii=False))
    return 1 if plan["readiness"] == "BLOCKED" else 0
