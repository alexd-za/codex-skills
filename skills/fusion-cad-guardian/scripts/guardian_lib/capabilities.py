from __future__ import annotations

import datetime as dt
from typing import Any

from .contracts import iter_requirements, validate_contract
from .errors import GuardianError

PROFILE_SCHEMA_URI = (
    "https://raw.githubusercontent.com/alexd-za/codex-skills/main/skills/"
    "fusion-cad-guardian/schemas/capability-profile.schema.json"
)

CAPABILITY_KEYS = (
    "connect",
    "inspect_active_document",
    "read_units",
    "save_checkpoint",
    "inspect_component_structure",
    "read_parameters",
    "inspect_feature_health",
    "measure_geometry",
    "query_mass_properties",
    "test_joints",
    "check_interference",
    "export_stl",
    "export_3mf",
    "capture_viewport",
)
VALID_CAPABILITY_STATUSES = {"available", "unavailable", "unknown"}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def default_capability_profile(server_name: str = "Fusion MCP") -> dict[str, Any]:
    return {
        "$schema": PROFILE_SCHEMA_URI,
        "schema_version": 1,
        "server": {"name": server_name, "transport": "", "endpoint": "", "discovered_at": ""},
        "capabilities": {key: {"status": "unknown", "tool": "", "method": "", "notes": ""} for key in CAPABILITY_KEYS},
        "notes": [
            "Populate this profile only after inspecting the connected MCP server's actual tools.",
            "Do not infer availability from the server name alone.",
        ],
    }


def validate_capability_profile(data: Any) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise GuardianError("capability profile must be a JSON object")
    allowed_top = {"$schema", "schema_version", "server", "capabilities", "notes"}
    unknown = set(data) - allowed_top
    if unknown:
        raise GuardianError(f"unknown capability profile fields: {sorted(unknown)}")
    if data.get("schema_version", 1) != 1:
        raise GuardianError("only capability profile schema_version 1 is supported")
    if "$schema" in data and not isinstance(data["$schema"], str):
        raise GuardianError("capability profile $schema must be a string")
    server = data.get("server", {})
    if not isinstance(server, dict):
        raise GuardianError("capability profile server must be an object")
    unknown_server = set(server) - {"name", "transport", "endpoint", "discovered_at"}
    if unknown_server:
        raise GuardianError(f"unknown server fields: {sorted(unknown_server)}")
    for key in ("name", "transport", "endpoint", "discovered_at"):
        if key in server and not isinstance(server[key], str):
            raise GuardianError(f"server.{key} must be a string")
    capabilities = data.get("capabilities", {})
    if not isinstance(capabilities, dict):
        raise GuardianError("capabilities must be an object")
    unknown_capabilities = set(capabilities) - set(CAPABILITY_KEYS)
    if unknown_capabilities:
        raise GuardianError(f"unknown capabilities: {sorted(unknown_capabilities)}")
    for key in CAPABILITY_KEYS:
        entry = capabilities.get(key)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise GuardianError(f"capabilities.{key} must be an object")
        unknown_entry = set(entry) - {"status", "tool", "method", "notes"}
        if unknown_entry:
            raise GuardianError(f"capabilities.{key} has unknown fields: {sorted(unknown_entry)}")
        status = entry.get("status", "unknown")
        if status not in VALID_CAPABILITY_STATUSES:
            raise GuardianError(f"capabilities.{key}.status must be one of {sorted(VALID_CAPABILITY_STATUSES)}")
        for field in ("tool", "method", "notes"):
            if field in entry and not isinstance(entry[field], str):
                raise GuardianError(f"capabilities.{key}.{field} must be a string")
        if status == "available" and not (str(entry.get("tool", "")).strip() or str(entry.get("method", "")).strip()):
            raise GuardianError(f"capabilities.{key} marked available requires a concrete tool or method")
    notes = data.get("notes", [])
    if not isinstance(notes, list) or any(not isinstance(note, str) for note in notes):
        raise GuardianError("capability profile notes must be an array of strings")
    return data


def set_capability(profile: dict[str, Any], capability: str, status: str, *, tool: str = "", method: str = "", notes: str = "") -> dict[str, Any]:
    profile = validate_capability_profile(profile)
    if capability not in CAPABILITY_KEYS:
        raise GuardianError(f"unknown capability: {capability}")
    if status not in VALID_CAPABILITY_STATUSES:
        raise GuardianError(f"invalid capability status: {status}")
    profile.setdefault("capabilities", {})[capability] = {"status": status, "tool": tool, "method": method, "notes": notes}
    if not profile.setdefault("server", {}).get("discovered_at"):
        profile["server"]["discovered_at"] = utc_now()
    return validate_capability_profile(profile)


def build_verification_plan(contract: dict[str, Any], profile: dict[str, Any]) -> dict[str, Any]:
    contract = validate_contract(contract)
    profile = validate_capability_profile(profile)
    capability_entries = profile.get("capabilities", {})
    routes: list[dict[str, Any]] = []
    blockers: list[str] = []
    discovery: list[str] = []
    for item in iter_requirements(contract):
        capability = item.get("capability")
        required = bool(item.get("required", True))
        if not capability:
            status, route, reason = "REVIEW", "fusion_mcp_or_human", "requirement has no declared MCP capability mapping"
        else:
            entry = capability_entries.get(capability, {"status": "unknown"})
            availability = entry.get("status", "unknown")
            if availability == "available":
                status, route, reason = "READY", "fusion_mcp", entry.get("tool") or entry.get("method") or "available MCP capability"
            elif availability == "unavailable":
                status, route = ("BLOCKED", "manual_or_external_evidence") if required else ("OPTIONAL_EXTERNAL", "manual_or_external_evidence")
                reason = entry.get("notes") or "MCP capability explicitly unavailable"
                if required:
                    blockers.append(item["qualified_id"])
            else:
                status, route, reason = "DISCOVER", "inspect_mcp_tools", "capability availability is unknown"
                discovery.append(item["qualified_id"])
        routes.append({
            "requirement_id": item["qualified_id"], "part_id": item.get("part_id"),
            "description": item.get("description", ""), "required": required,
            "capability": capability, "status": status, "route": route, "reason": reason,
        })
    readiness = "BLOCKED" if blockers else "DISCOVERY_REQUIRED" if discovery else "READY"
    return {
        "schema_version": 1, "generated_at": utc_now(), "server": profile.get("server", {}),
        "readiness": readiness, "routes": routes, "required_blockers": blockers,
        "discovery_required": discovery,
        "guardrail": "Fusion MCP remains the sole live-CAD controller; Guardian only plans and verifies.",
    }
