"""Argument parser and CLI entry point for Fusion CAD Guardian."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from . import VERSION
from .capabilities import CAPABILITY_KEYS
from .errors import GuardianError
from .limits import DEFAULT_RESOURCE_LIMITS
from .cli_commands import (
    _cmd_audit,
    _cmd_batch,
    _cmd_bundle,
    _cmd_bundle_verify,
    _cmd_capabilities_init,
    _cmd_capabilities_set,
    _cmd_compare,
    _cmd_doctor,
    _cmd_evidence_hash,
    _cmd_evidence_init,
    _cmd_gate,
    _cmd_init,
    _cmd_inspect_3mf,
    _cmd_migrate,
    _cmd_part_add,
    _cmd_plan,
    _cmd_project,
    _cmd_self_test,
    _cmd_slicer_audit,
    _cmd_validate,
    _parse_part,
)

def _add_resource_limit_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--max-file-size-mb", type=float, default=DEFAULT_RESOURCE_LIMITS.max_file_size_mb)
    parser.add_argument("--max-input-triangles", type=int, default=DEFAULT_RESOURCE_LIMITS.max_triangles)
    parser.add_argument("--max-coordinate-abs-mm", type=float, default=DEFAULT_RESOURCE_LIMITS.max_coordinate_abs_mm)
    parser.add_argument("--max-estimated-memory-mb", type=float, default=DEFAULT_RESOURCE_LIMITS.max_estimated_memory_mb)
    parser.add_argument("--max-archive-entries", type=int, default=DEFAULT_RESOURCE_LIMITS.max_archive_entries)
    parser.add_argument("--max-archive-uncompressed-mb", type=float, default=DEFAULT_RESOURCE_LIMITS.max_archive_uncompressed_mb)
    parser.add_argument("--max-compression-ratio", type=float, default=DEFAULT_RESOURCE_LIMITS.max_compression_ratio)


def _add_report_outputs(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--json", dest="json_out")
    parser.add_argument("--markdown")
    parser.add_argument("--html")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verification and manufacturing-evidence support for Autodesk Fusion MCP workflows")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="create a schema-v2.2 design contract")
    init.add_argument("--out", required=True); init.add_argument("--part-name", default="Example Part")
    init.add_argument("--task-type", choices=("part", "assembly"), default="part")
    init.add_argument("--part", action="append", type=_parse_part); init.add_argument("--force", action="store_true")
    init.set_defaults(func=_cmd_init)

    part_add = sub.add_parser("part-add", help="add a part template to an existing contract")
    part_add.add_argument("contract"); part_add.add_argument("--id", required=True); part_add.add_argument("--name", required=True)
    part_add.add_argument("--out"); part_add.add_argument("--force", action="store_true"); part_add.set_defaults(func=_cmd_part_add)

    project = sub.add_parser("project", help="create a complete Guardian project workspace")
    project.add_argument("directory"); project.add_argument("--name", required=True)
    project.add_argument("--task-type", choices=("part", "assembly"), default="part"); project.add_argument("--part", action="append", type=_parse_part)
    project.set_defaults(func=_cmd_project)

    evidence_init = sub.add_parser("evidence-init", help="create an evidence ledger from a contract")
    evidence_init.add_argument("--contract", required=True); evidence_init.add_argument("--out", required=True); evidence_init.add_argument("--force", action="store_true")
    evidence_init.set_defaults(func=_cmd_evidence_init)
    evidence_hash = sub.add_parser("evidence-hash", help="populate export SHA-256 values")
    evidence_hash.add_argument("evidence"); evidence_hash.add_argument("--out"); evidence_hash.set_defaults(func=_cmd_evidence_hash)

    cap_init = sub.add_parser("capabilities-init", help="create a Fusion MCP capability profile")
    cap_init.add_argument("--out", required=True); cap_init.add_argument("--server-name", default="Fusion MCP"); cap_init.add_argument("--force", action="store_true")
    cap_init.set_defaults(func=_cmd_capabilities_init)
    cap_set = sub.add_parser("capabilities-set", help="set one discovered MCP capability")
    cap_set.add_argument("profile"); cap_set.add_argument("capability", choices=CAPABILITY_KEYS); cap_set.add_argument("status", choices=("available", "unavailable", "unknown"))
    cap_set.add_argument("--tool"); cap_set.add_argument("--method"); cap_set.add_argument("--notes"); cap_set.add_argument("--out"); cap_set.set_defaults(func=_cmd_capabilities_set)
    plan = sub.add_parser("plan", help="route contract requirements against MCP capabilities")
    plan.add_argument("--contract", required=True); plan.add_argument("--capabilities", required=True); plan.add_argument("--json", dest="json_out"); plan.set_defaults(func=_cmd_plan)

    validate = sub.add_parser("validate", help="validate a Guardian JSON file")
    validate.add_argument("kind", choices=("contract", "evidence", "capabilities", "audit-report", "slicer-report", "bundle-manifest")); validate.add_argument("file"); validate.set_defaults(func=_cmd_validate)

    audit = sub.add_parser("audit", help="audit an STL or selected 3MF object")
    audit.add_argument("mesh"); audit.add_argument("--contract"); audit.add_argument("--part-id")
    audit.add_argument("--object-id"); audit.add_argument("--object-name"); _add_report_outputs(audit)
    audit.add_argument("--weld-tolerance", type=float, default=1e-6); audit.add_argument("--area-epsilon", type=float, default=1e-12)
    audit.add_argument("--sliver-quality-threshold", type=float, default=0.05); _add_resource_limit_arguments(audit); audit.set_defaults(func=_cmd_audit)

    inspect = sub.add_parser("inspect-3mf", help="list 3MF objects and build items without auditing")
    inspect.add_argument("mesh"); inspect.add_argument("--json", dest="json_out"); _add_resource_limit_arguments(inspect); inspect.set_defaults(func=_cmd_inspect_3mf)

    slicer = sub.add_parser("slicer-audit", help="parse existing G-code into source-linked manufacturing evidence")
    slicer.add_argument("gcode"); slicer.add_argument("--source-mesh"); slicer.add_argument("--contract"); slicer.add_argument("--part-id")
    _add_report_outputs(slicer); _add_resource_limit_arguments(slicer); slicer.set_defaults(func=_cmd_slicer_audit)

    compare = sub.add_parser("compare", help="compare two audit reports for the same part/object")
    compare.add_argument("before"); compare.add_argument("after"); _add_report_outputs(compare); compare.set_defaults(func=_cmd_compare)

    batch = sub.add_parser("batch", help="audit STL/3MF jobs from a batch manifest")
    batch.add_argument("manifest"); batch.add_argument("--out-dir", required=True)
    batch.add_argument("--weld-tolerance", type=float, default=1e-6); batch.add_argument("--area-epsilon", type=float, default=1e-12)
    batch.add_argument("--sliver-quality-threshold", type=float, default=0.05); _add_resource_limit_arguments(batch); batch.set_defaults(func=_cmd_batch)

    acceptance = sub.add_parser("gate", help="combine Fusion, mesh, and optional slicer evidence")
    acceptance.add_argument("--contract", required=True); acceptance.add_argument("--evidence", required=True)
    acceptance.add_argument("--mesh-report", action="append", required=True); acceptance.add_argument("--slicer-report", action="append")
    _add_report_outputs(acceptance); acceptance.set_defaults(func=_cmd_gate)

    bundle = sub.add_parser("bundle", help="create an integrity-checked verification bundle from a Guardian project")
    bundle.add_argument("--project", required=True); bundle.add_argument("--out", required=True); bundle.add_argument("--include-exports", action="store_true"); _add_resource_limit_arguments(bundle); bundle.set_defaults(func=_cmd_bundle)
    bundle_verify = sub.add_parser("bundle-verify", help="verify a Guardian bundle manifest and all file hashes")
    bundle_verify.add_argument("bundle"); bundle_verify.add_argument("--json", dest="json_out"); _add_resource_limit_arguments(bundle_verify); bundle_verify.set_defaults(func=_cmd_bundle_verify)

    migrate = sub.add_parser("migrate", help="migrate a schema-version 2 contract to revision 2.2")
    migrate.add_argument("contract"); migrate.add_argument("--out"); migrate.add_argument("--force", action="store_true"); migrate.set_defaults(func=_cmd_migrate)
    doctor = sub.add_parser("doctor", help="run installation and optional project diagnostics")
    doctor.add_argument("--project"); doctor.add_argument("--json", dest="json_out"); doctor.set_defaults(func=_cmd_doctor)
    self_test = sub.add_parser("self-test", help="run built-in validation tests"); self_test.set_defaults(func=_cmd_self_test)
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
