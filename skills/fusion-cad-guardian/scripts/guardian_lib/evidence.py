from __future__ import annotations

from pathlib import Path
from typing import Any

from .contracts import VALID_STATUSES, validate_contract
from .core import GuardianError, sha256_file

EVIDENCE_KEYS = {"schema_version", "design", "checks", "exports", "notes"}
CHECK_KEYS = {"id", "status", "method", "evidence", "source", "required", "timestamp"}
EXPORT_KEYS = {"mesh", "mesh_sha256", "component", "body", "document", "checkpoint", "method"}
ALLOWED_SOURCES = {
    "fusion_mcp", "human_review", "calculation", "simulation",
    "physical_test", "slicer", "other",
}


def default_evidence(contract: dict[str, Any]) -> dict[str, Any]:
    contract = validate_contract(contract)
    fusion = contract.get("fusion_requirements", []) if contract.get("schema_version") == 2 else []
    engineering = contract.get("engineering_requirements", []) if contract.get("schema_version") == 2 else []
    return {
        "schema_version": 1,
        "design": {
            "document": "",
            "checkpoint": "",
            "units": contract.get("units", "mm"),
            "fusion_mcp_server": "",
        },
        "checks": [
            {
                "id": item["id"],
                "required": bool(item.get("required", True)),
                "status": "NOT_VERIFIED",
                "method": "",
                "evidence": "",
                "source": "fusion_mcp" if item in fusion else "human_review",
            }
            for item in fusion + engineering
        ],
        "exports": [],
        "notes": [
            "Populate this ledger only with evidence actually gathered through Fusion MCP, calculations, simulation, slicer review, physical testing, or human review."
        ],
    }


def validate_evidence(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise GuardianError("evidence ledger must be a JSON object")
    unknown = set(data) - EVIDENCE_KEYS
    if unknown:
        raise GuardianError(f"unknown evidence fields: {sorted(unknown)}")
    if data.get("schema_version", 1) != 1:
        raise GuardianError("only evidence schema_version 1 is supported")
    design = data.get("design", {})
    if not isinstance(design, dict):
        raise GuardianError("evidence.design must be an object")
    for key, value in design.items():
        if not isinstance(value, str):
            raise GuardianError(f"evidence.design.{key} must be a string")

    checks = data.get("checks", [])
    if not isinstance(checks, list):
        raise GuardianError("evidence.checks must be an array")
    seen: set[str] = set()
    for index, check in enumerate(checks):
        if not isinstance(check, dict):
            raise GuardianError(f"evidence.checks[{index}] must be an object")
        extra = set(check) - CHECK_KEYS
        if extra:
            raise GuardianError(f"evidence.checks[{index}] has unknown keys: {sorted(extra)}")
        check_id = check.get("id")
        if not isinstance(check_id, str) or not check_id.strip():
            raise GuardianError(f"evidence.checks[{index}].id must be a non-empty string")
        if check_id in seen:
            raise GuardianError(f"duplicate evidence check id: {check_id}")
        seen.add(check_id)
        status = check.get("status")
        if status not in VALID_STATUSES:
            raise GuardianError(f"evidence check {check_id} has invalid status: {status}")
        if not isinstance(check.get("required", True), bool):
            raise GuardianError(f"evidence check {check_id}.required must be boolean")
        for key in ("method", "evidence", "source", "timestamp"):
            if key in check and not isinstance(check[key], str):
                raise GuardianError(f"evidence check {check_id}.{key} must be a string")
        source = check.get("source", "")
        if source and source not in ALLOWED_SOURCES:
            raise GuardianError(
                f"evidence check {check_id}.source must be one of {sorted(ALLOWED_SOURCES)}"
            )
        if status in {"PASS", "FAIL"}:
            if not check.get("method", "").strip() or not check.get("evidence", "").strip():
                raise GuardianError(f"{status} evidence check {check_id} requires method and evidence")
        if status == "NOT_APPLICABLE" and not check.get("evidence", "").strip():
            raise GuardianError(f"NOT_APPLICABLE evidence check {check_id} requires a rationale")

    exports = data.get("exports", [])
    if not isinstance(exports, list):
        raise GuardianError("evidence.exports must be an array")
    for index, export in enumerate(exports):
        if not isinstance(export, dict):
            raise GuardianError(f"evidence.exports[{index}] must be an object")
        extra = set(export) - EXPORT_KEYS
        if extra:
            raise GuardianError(f"evidence.exports[{index}] has unknown keys: {sorted(extra)}")
        for key in EXPORT_KEYS:
            if key in export and not isinstance(export[key], str):
                raise GuardianError(f"evidence.exports[{index}].{key} must be a string")
        if not export.get("mesh", "").strip():
            raise GuardianError(f"evidence.exports[{index}].mesh must be non-empty")
        mesh_hash = export.get("mesh_sha256", "")
        if mesh_hash and (
            len(mesh_hash) != 64 or any(char not in "0123456789abcdefABCDEF" for char in mesh_hash)
        ):
            raise GuardianError(f"evidence.exports[{index}].mesh_sha256 must be a SHA-256 hex string")
    notes = data.get("notes", [])
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise GuardianError("evidence.notes must be an array of strings")
    return data


def _requirement_map(contract: dict[str, Any]) -> dict[str, dict[str, Any]]:
    if contract.get("schema_version") != 2:
        return {}
    items = contract.get("fusion_requirements", []) + contract.get("engineering_requirements", [])
    return {item["id"]: item for item in items}


def evaluate_evidence(contract: dict[str, Any], evidence: dict[str, Any]) -> dict[str, Any]:
    contract = validate_contract(contract)
    evidence = validate_evidence(evidence)
    requirements = _requirement_map(contract)
    evidence_map = {item["id"]: item for item in evidence.get("checks", [])}
    checks: list[dict[str, Any]] = []
    for check_id, requirement in requirements.items():
        item = evidence_map.get(check_id)
        if item is None:
            checks.append({
                "id": check_id,
                "required": bool(requirement.get("required", True)),
                "status": "NOT_VERIFIED",
                "reason": "missing evidence entry",
            })
            continue
        checks.append({
            "id": check_id,
            "required": bool(requirement.get("required", True)),
            "status": item["status"],
            "method": item.get("method", ""),
            "evidence": item.get("evidence", ""),
            "source": item.get("source", ""),
            "timestamp": item.get("timestamp", ""),
        })
    required_fail = [item for item in checks if item["required"] and item["status"] == "FAIL"]
    required_unknown = [
        item for item in checks
        if item["required"] and item["status"] in {"NOT_VERIFIED", "NOT_APPLICABLE"}
    ]
    optional_open = [
        item for item in checks
        if not item["required"] and item["status"] in {"FAIL", "NOT_VERIFIED"}
    ]
    if required_fail:
        verdict = "FAIL"
    elif required_unknown:
        verdict = "INCOMPLETE"
    elif optional_open:
        verdict = "CONDITIONAL_PASS"
    else:
        verdict = "PASS"
    return {
        "checks": checks,
        "required_failures": [item["id"] for item in required_fail],
        "required_not_verified": [item["id"] for item in required_unknown],
        "optional_open_items": [item["id"] for item in optional_open],
        "verdict": verdict,
    }


def _complete_export_record(item: dict[str, Any]) -> tuple[bool, list[str]]:
    missing = []
    for key in ("mesh", "mesh_sha256", "document", "checkpoint", "method"):
        if not item.get(key, "").strip():
            missing.append(key)
    if not item.get("component", "").strip() and not item.get("body", "").strip():
        missing.append("component_or_body")
    return not missing, missing


def verify_export_provenance(
    contract: dict[str, Any], evidence: dict[str, Any], mesh_reports: list[dict[str, Any]]
) -> dict[str, Any]:
    required = bool(contract.get("export_provenance_required", False)) if contract.get("schema_version") == 2 else False
    exports = evidence.get("exports", [])
    results: list[dict[str, Any]] = []
    for report in mesh_reports:
        report_mesh = report.get("mesh", {})
        report_hash = report_mesh.get("sha256")
        report_path = report_mesh.get("path")
        matches = [item for item in exports if item.get("mesh_sha256", "").lower() == str(report_hash or "").lower()]
        complete = []
        incomplete = []
        for item in matches:
            valid, missing = _complete_export_record(item)
            (complete if valid else incomplete).append({"record": item, "missing": missing})
        if complete:
            status, reason = "PASS", "matching export record with complete provenance"
        elif matches:
            status, reason = "INCOMPLETE", "matching export record is missing provenance fields"
        else:
            status = "INCOMPLETE" if required else "NOT_APPLICABLE"
            reason = "no export record matches the audited mesh SHA-256"
        results.append({
            "mesh": report_path,
            "sha256": report_hash,
            "status": status,
            "reason": reason,
            "matching_exports": [entry["record"] for entry in complete],
            "incomplete_matches": incomplete,
        })
    if not required:
        verdict = "NOT_APPLICABLE"
    elif results and all(item["status"] == "PASS" for item in results):
        verdict = "PASS"
    else:
        verdict = "INCOMPLETE"
    return {"required": required, "results": results, "verdict": verdict}


def populate_export_hashes(evidence: dict[str, Any], base_dir: Path) -> dict[str, Any]:
    evidence = validate_evidence(evidence)
    for item in evidence.get("exports", []):
        mesh = item.get("mesh")
        if not mesh:
            continue
        path = Path(mesh)
        if not path.is_absolute():
            path = base_dir / path
        if not path.is_file():
            raise GuardianError(f"export mesh not found: {path}")
        item["mesh_sha256"] = sha256_file(path)
    return evidence


def gate(
    contract: dict[str, Any],
    evidence: dict[str, Any],
    mesh_reports: list[dict[str, Any]],
    *,
    expected_contract_sha256: str | None = None,
) -> dict[str, Any]:
    contract = validate_contract(contract)
    evidence = validate_evidence(evidence)
    evidence_result = evaluate_evidence(contract, evidence)
    provenance = verify_export_provenance(contract, evidence, mesh_reports)

    mesh_validation: list[dict[str, Any]] = []
    for report in mesh_reports:
        verdict = report.get("verdict")
        report_contract_hash = report.get("contract", {}).get("sha256")
        if verdict == "FAIL":
            status, reason = "FAIL", "mesh contract checks failed"
        elif verdict != "PASS":
            status, reason = "INCOMPLETE", "mesh report is audit-only or has no passing contract verdict"
        elif expected_contract_sha256 and report_contract_hash != expected_contract_sha256:
            status, reason = "INCOMPLETE", "mesh report was not generated from the current contract"
        else:
            status, reason = "PASS", "mesh report passed and is linked to the current contract"
        mesh_validation.append({
            "path": report.get("mesh", {}).get("path"),
            "sha256": report.get("mesh", {}).get("sha256"),
            "verdict": verdict,
            "contract_sha256": report_contract_hash,
            "status": status,
            "reason": reason,
        })

    if any(item["status"] == "FAIL" for item in mesh_validation) or evidence_result["verdict"] == "FAIL":
        verdict = "FAIL"
    elif (
        not mesh_validation
        or any(item["status"] == "INCOMPLETE" for item in mesh_validation)
        or evidence_result["verdict"] == "INCOMPLETE"
        or provenance["verdict"] == "INCOMPLETE"
    ):
        verdict = "INCOMPLETE"
    elif evidence_result["verdict"] == "CONDITIONAL_PASS":
        verdict = "CONDITIONAL_PASS"
    else:
        verdict = "PASS"
    return {
        "overall_verdict": verdict,
        "evidence": evidence_result,
        "export_provenance": provenance,
        "mesh_reports": mesh_validation,
    }
