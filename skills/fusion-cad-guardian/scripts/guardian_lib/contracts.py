from __future__ import annotations

import re
from typing import Any

from .errors import GuardianError
from .limits import DEFAULT_RESOURCE_LIMITS, limits_from_mapping

CONTRACT_SCHEMA_URI = "https://raw.githubusercontent.com/alexd-za/codex-skills/main/skills/fusion-cad-guardian/schemas/contract.schema.json"
VALID_STATUSES = {"PASS", "FAIL", "NOT_VERIFIED", "NOT_APPLICABLE"}
ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]*$")
MESH_KEYS = {
    "expected_dimensions_mm", "volume_mm3", "surface_area_mm2", "mass_g", "density_g_cm3",
    "require_watertight", "max_shells", "max_boundary_edges", "max_nonmanifold_edges",
    "max_degenerate_triangles", "max_duplicate_triangles", "max_inconsistent_winding_edges",
    "max_sliver_triangles", "min_triangle_quality", "min_triangles", "max_triangles",
    "require_positive_signed_volume", "build_plate", "orientation",
}


def _requirement(id_: str, description: str, capability: str | None = None, required: bool = True) -> dict[str, Any]:
    item: dict[str, Any] = {"id": id_, "required": required, "description": description}
    if capability:
        item["capability"] = capability
    return item


def default_fusion_requirements(task_type: str = "part") -> list[dict[str, Any]]:
    items = [
        _requirement("active_document", "Active Fusion document and design context confirmed", "inspect_active_document"),
        _requirement("safe_checkpoint", "Original design preserved by save, version, copy, or explicit checkpoint", "save_checkpoint"),
        _requirement("units_confirmed", "Design units confirmed", "read_units"),
        _requirement("component_structure", "Expected components and bodies verified", "inspect_component_structure"),
        _requirement("critical_parameters", "Critical dimensions or named parameters verified in Fusion", "read_parameters"),
        _requirement("feature_health", "No unresolved feature or timeline failures", "inspect_feature_health"),
        _requirement("export_selection", "Exported body/component matches the intended final candidate", "export_stl"),
    ]
    if task_type == "assembly":
        items += [
            _requirement("joints_verified", "Joint type, axis, limits, and intended degrees of freedom verified", "test_joints"),
            _requirement("motion_sampled", "Neutral, extreme, and representative intermediate positions inspected", "test_joints"),
            _requirement("interference_checked", "Interference checked at representative positions", "check_interference"),
        ]
    return items


def default_mesh_contract() -> dict[str, Any]:
    return {
        "expected_dimensions_mm": {a: {"target": v, "tolerance": 0.1} for a, v in (("x", 20.0), ("y", 20.0), ("z", 10.0))},
        "require_watertight": True, "max_shells": 1, "max_boundary_edges": 0,
        "max_nonmanifold_edges": 0, "max_degenerate_triangles": 0,
        "max_duplicate_triangles": 0, "max_inconsistent_winding_edges": 0,
        "max_sliver_triangles": 0, "min_triangle_quality": 0.01,
        "min_triangles": 12, "max_triangles": 2_000_000,
        "require_positive_signed_volume": True,
    }


def default_part(part_id: str, name: str) -> dict[str, Any]:
    return {
        "id": part_id, "name": name, "required": True, "mesh": default_mesh_contract(),
        "fusion_requirements": [
            _requirement("component_present", "Part component/body exists and is uniquely identifiable", "inspect_component_structure"),
            _requirement("critical_parameters", "Part-specific critical parameters verified", "read_parameters"),
            _requirement("feature_health", "Part-specific feature history has no unresolved failures", "inspect_feature_health"),
            _requirement("export_selection", "Correct part body/component selected for export", "export_stl"),
        ],
        "engineering_requirements": [],
        "notes": ["Replace placeholder mesh dimensions with this part's actual acceptance criteria."],
    }


def default_contract(part_name: str, task_type: str = "part", parts: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    if task_type not in {"part", "assembly"}:
        raise GuardianError("task_type must be part or assembly")
    result = {
        "$schema": CONTRACT_SCHEMA_URI, "schema_version": 2, "schema_revision": "2.1",
        "part_name": part_name, "task_type": task_type, "units": "mm",
        "mesh": default_mesh_contract(), "parts": [],
        "fusion_requirements": default_fusion_requirements(task_type),
        "engineering_requirements": [
            _requirement("material_confirmed", "Material and manufacturing process confirmed", required=False),
            _requirement("loads_reviewed", "Expected loads, torque, impact, and safety factors reviewed", required=False),
            _requirement("tolerances_reviewed", "Fits, clearances, shrinkage, and manufacturing tolerances reviewed", required=False),
            _requirement("physical_test_planned", "Physical fit/function test planned before competition or deployment", required=False),
        ],
        "assembly_requirements": [], "export_provenance_required": True,
        "resource_limits": DEFAULT_RESOURCE_LIMITS.to_dict(),
        "notes": ["Replace example dimensions with actual acceptance criteria.", "Mesh checks do not verify wall thickness, joints, strength, or local feature tolerances.", "When parts is non-empty, audit each export with --part-id."],
    }
    if parts:
        result["mesh"] = {}
        result["parts"] = [default_part(i, n) for i, n in parts]
    return result


def _id(value: Any, label: str) -> str:
    if not isinstance(value, str) or not ID_RE.fullmatch(value):
        raise GuardianError(f"{label} must match {ID_RE.pattern}")
    return value


def _range(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise GuardianError(f"{label} must be a non-empty object")
    if set(value) - {"target", "tolerance", "min", "max"}:
        raise GuardianError(f"{label} has unknown keys")
    if "target" in value:
        if set(value) != {"target", "tolerance"} or float(value["tolerance"]) < 0:
            raise GuardianError(f"{label} target requires non-negative target+tolerance")
    elif not ({"min", "max"} & set(value)):
        raise GuardianError(f"{label} requires target+tolerance or min/max")
    for key, item in value.items():
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            raise GuardianError(f"{label}.{key} must be numeric")
    if "min" in value and "max" in value and value["min"] > value["max"]:
        raise GuardianError(f"{label}.min cannot exceed max")


def _requirements(items: Any, label: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise GuardianError(f"{label} must be an array")
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict) or set(item) - {"id", "required", "description", "capability"}:
            raise GuardianError(f"{label}[{index}] is invalid")
        item_id = _id(item.get("id"), f"{label}[{index}].id")
        if item_id in seen:
            raise GuardianError(f"duplicate requirement id in {label}: {item_id}")
        seen.add(item_id)
        if not isinstance(item.get("required", True), bool) or not isinstance(item.get("description", ""), str):
            raise GuardianError(f"{label}[{index}] has invalid required/description")
        if item.get("capability") is not None:
            _id(item["capability"], f"{label}[{index}].capability")
    return items


def _mesh(mesh: Any, label: str = "mesh") -> dict[str, Any]:
    if not isinstance(mesh, dict) or set(mesh) - MESH_KEYS:
        raise GuardianError(f"{label} is invalid")
    dims = mesh.get("expected_dimensions_mm", {})
    if not isinstance(dims, dict) or set(dims) - {"x", "y", "z"}:
        raise GuardianError(f"{label}.expected_dimensions_mm is invalid")
    for axis, value in dims.items():
        _range(value, f"{label}.expected_dimensions_mm.{axis}")
    for key in ("volume_mm3", "surface_area_mm2", "mass_g"):
        if key in mesh:
            _range(mesh[key], f"{label}.{key}")
    if "density_g_cm3" in mesh and (float(mesh["density_g_cm3"]) <= 0 or "mass_g" not in mesh):
        raise GuardianError(f"{label}.density_g_cm3 requires positive density and mass_g")
    for key in ("max_shells", "max_boundary_edges", "max_nonmanifold_edges", "max_degenerate_triangles", "max_duplicate_triangles", "max_inconsistent_winding_edges", "max_sliver_triangles", "min_triangles", "max_triangles"):
        if key in mesh and (isinstance(mesh[key], bool) or not isinstance(mesh[key], int) or mesh[key] < 0):
            raise GuardianError(f"{label}.{key} must be a non-negative integer")
    if "min_triangle_quality" in mesh and not 0 <= float(mesh["min_triangle_quality"]) <= 1:
        raise GuardianError(f"{label}.min_triangle_quality must be between 0 and 1")
    plate = mesh.get("build_plate")
    if plate is not None:
        if not isinstance(plate, dict) or set(plate) - {"axis", "plane_mm", "tolerance_mm", "min_contact_vertices", "min_contact_area_mm2"} or plate.get("axis") not in {"x", "y", "z"}:
            raise GuardianError(f"{label}.build_plate is invalid")
    orientation = mesh.get("orientation")
    if orientation is not None:
        if not isinstance(orientation, dict) or set(orientation) - {"build_axis", "severe_overhang_angle_degrees", "max_severe_downward_area_mm2"} or orientation.get("build_axis", "z") not in {"x", "y", "z"}:
            raise GuardianError(f"{label}.orientation is invalid")
    return mesh


def validate_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise GuardianError("contract must be a JSON object")
    version = contract.get("schema_version", 1)
    if version == 1:
        if contract.get("units", "mm") != "mm":
            raise GuardianError("contract units must be mm")
        _mesh({k: v for k, v in contract.items() if k in MESH_KEYS})
        return contract
    allowed = {"$schema", "schema_version", "schema_revision", "part_name", "task_type", "units", "mesh", "parts", "fusion_requirements", "engineering_requirements", "assembly_requirements", "export_provenance_required", "resource_limits", "notes"}
    if version != 2 or set(contract) - allowed:
        raise GuardianError("invalid schema-v2 contract fields")
    if contract.get("units", "mm") != "mm" or contract.get("task_type", "part") not in {"part", "assembly"}:
        raise GuardianError("invalid units or task_type")
    _mesh(contract.get("mesh", {}))
    parts = contract.get("parts", [])
    if not isinstance(parts, list):
        raise GuardianError("parts must be an array")
    part_ids: set[str] = set()
    for i, part in enumerate(parts):
        if not isinstance(part, dict) or set(part) - {"id", "name", "required", "mesh", "fusion_requirements", "engineering_requirements", "notes"}:
            raise GuardianError(f"parts[{i}] is invalid")
        pid = _id(part.get("id"), f"parts[{i}].id")
        if pid in part_ids:
            raise GuardianError(f"duplicate part id: {pid}")
        part_ids.add(pid)
        if not isinstance(part.get("name"), str) or not part["name"].strip() or not isinstance(part.get("required", True), bool):
            raise GuardianError(f"parts[{i}] name/required invalid")
        _mesh(part.get("mesh", {}), f"parts[{i}].mesh")
        _requirements(part.get("fusion_requirements", []), f"parts[{i}].fusion_requirements")
        _requirements(part.get("engineering_requirements", []), f"parts[{i}].engineering_requirements")
    if parts and contract.get("mesh"):
        raise GuardianError("use either top-level mesh or parts[].mesh, not both")
    groups = [contract.get("fusion_requirements", []), contract.get("engineering_requirements", []), contract.get("assembly_requirements", [])]
    all_ids: list[str] = []
    for label, group in zip(("fusion_requirements", "engineering_requirements", "assembly_requirements"), groups):
        all_ids += [x["id"] for x in _requirements(group, label)]
    if len(all_ids) != len(set(all_ids)):
        raise GuardianError("duplicate top-level requirement ids")
    if not isinstance(contract.get("export_provenance_required", True), bool):
        raise GuardianError("export_provenance_required must be boolean")
    limits_from_mapping(contract.get("resource_limits"), base=DEFAULT_RESOURCE_LIMITS)
    return contract


def get_part(contract: dict[str, Any], part_id: str) -> dict[str, Any]:
    for part in validate_contract(contract).get("parts", []):
        if part["id"] == part_id:
            return part
    raise GuardianError(f"part_id not found in contract: {part_id}")


def resolve_mesh_contract(contract: dict[str, Any], part_id: str | None = None) -> tuple[dict[str, Any], str | None, str]:
    contract = validate_contract(contract)
    if contract.get("schema_version", 1) == 1:
        return ({k: v for k, v in contract.items() if k in MESH_KEYS}, None, contract.get("part_name", ""))
    parts = contract.get("parts", [])
    if parts:
        if part_id is None:
            if len(parts) != 1:
                raise GuardianError("contract contains multiple parts; audit requires --part-id")
            part = parts[0]
        else:
            part = get_part(contract, part_id)
        return part.get("mesh", {}), part["id"], part["name"]
    if part_id is not None:
        raise GuardianError("--part-id was provided but contract has no parts")
    return contract.get("mesh", {}), None, contract.get("part_name", "")


def mesh_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return resolve_mesh_contract(contract)[0]


def iter_requirements(contract: dict[str, Any]) -> list[dict[str, Any]]:
    contract = validate_contract(contract)
    if contract.get("schema_version", 1) != 2:
        return []
    out: list[dict[str, Any]] = []
    def add(items: list[dict[str, Any]], category: str, part_id: str | None = None) -> None:
        for item in items:
            out.append({**item, "qualified_id": f"{part_id}.{item['id']}" if part_id else item["id"], "part_id": part_id, "category": category})
    add(contract.get("fusion_requirements", []), "fusion")
    add(contract.get("engineering_requirements", []), "engineering")
    add(contract.get("assembly_requirements", []), "assembly")
    for part in contract.get("parts", []):
        add(part.get("fusion_requirements", []), "fusion", part["id"])
        add(part.get("engineering_requirements", []), "engineering", part["id"])
    return out


def _range_check(value: float, req: dict[str, Any]) -> tuple[bool, str]:
    if "target" in req:
        target, tolerance = float(req["target"]), float(req["tolerance"])
        return abs(value - target) <= tolerance, f"{target} ± {tolerance}"
    minimum, maximum = float(req.get("min", float("-inf"))), float(req.get("max", float("inf")))
    return minimum <= value <= maximum, f"[{minimum}, {maximum}]"


def evaluate_contract(metrics: dict[str, Any], contract: dict[str, Any], triangles: list[Any], *, part_id: str | None = None) -> list[dict[str, Any]]:
    from .core import build_plate_contact
    mesh, resolved, _ = resolve_mesh_contract(contract, part_id)
    checks: list[dict[str, Any]] = []
    def add(id_: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append({"id": id_, "part_id": resolved, "status": "PASS" if passed else "FAIL", "actual": actual, "expected": expected})
    for axis, req in mesh.get("expected_dimensions_mm", {}).items():
        actual = float(metrics["dimensions_mm"][axis])
        passed, expected = _range_check(actual, req)
        add(f"dimension_{axis}", passed, actual, expected)
    for key, metric in (("volume_mm3", "absolute_volume_mm3"), ("surface_area_mm2", "surface_area_mm2")):
        if key in mesh:
            actual = float(metrics[metric])
            passed, expected = _range_check(actual, mesh[key])
            add(key, passed, actual, expected)
    if "mass_g" in mesh:
        mass = float(metrics["absolute_volume_mm3"]) / 1000 * float(mesh["density_g_cm3"])
        passed, expected = _range_check(mass, mesh["mass_g"])
        add("mass_g", passed, mass, expected)
    maxima = {"max_shells":"shell_count", "max_boundary_edges":"boundary_edge_count", "max_nonmanifold_edges":"nonmanifold_edge_count", "max_degenerate_triangles":"degenerate_triangle_count", "max_duplicate_triangles":"duplicate_triangle_count", "max_inconsistent_winding_edges":"inconsistent_winding_edge_count", "max_sliver_triangles":"sliver_triangle_count", "max_triangles":"triangle_count"}
    for key, metric in maxima.items():
        if key in mesh:
            add(key, metrics[metric] <= mesh[key], metrics[metric], f"<= {mesh[key]}")
    if "min_triangles" in mesh:
        add("min_triangles", metrics["triangle_count"] >= mesh["min_triangles"], metrics["triangle_count"], f">= {mesh['min_triangles']}")
    if "min_triangle_quality" in mesh:
        actual = metrics["triangle_quality"]["minimum"]
        add("min_triangle_quality", actual >= mesh["min_triangle_quality"], actual, f">= {mesh['min_triangle_quality']}")
    if mesh.get("require_watertight"):
        add("watertight", bool(metrics["watertight"]), metrics["watertight"], True)
    if mesh.get("require_positive_signed_volume"):
        add("positive_signed_volume", metrics["signed_volume_mm3"] > 0, metrics["signed_volume_mm3"], "> 0")
    if "build_plate" in mesh:
        plate = mesh["build_plate"]
        contact = build_plate_contact(triangles, plate["axis"], float(plate.get("plane_mm", 0)), float(plate.get("tolerance_mm", .05)))
        if "min_contact_vertices" in plate:
            add("build_plate_contact_vertices", contact["vertex_count"] >= plate["min_contact_vertices"], contact["vertex_count"], f">= {plate['min_contact_vertices']}")
        if "min_contact_area_mm2" in plate:
            add("build_plate_contact_area", contact["area_mm2"] >= plate["min_contact_area_mm2"], contact["area_mm2"], f">= {plate['min_contact_area_mm2']}")
    if "orientation" in mesh and "max_severe_downward_area_mm2" in mesh["orientation"]:
        actual = metrics["severe_downward_area"]["area_mm2"]
        maximum = float(mesh["orientation"]["max_severe_downward_area_mm2"])
        add("max_severe_downward_area_mm2", actual <= maximum, actual, f"<= {maximum}")
    return checks
