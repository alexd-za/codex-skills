from __future__ import annotations

from typing import Any

from .core import GuardianError, Triangle, build_plate_contact

MESH_KEYS = {
    "expected_dimensions_mm", "volume_mm3", "surface_area_mm2", "mass_g",
    "density_g_cm3", "require_watertight", "max_shells", "max_boundary_edges",
    "max_nonmanifold_edges", "max_degenerate_triangles", "max_duplicate_triangles",
    "max_inconsistent_winding_edges", "max_sliver_triangles", "min_triangle_quality",
    "min_triangles", "max_triangles", "require_positive_signed_volume", "build_plate",
    "orientation",
}
TOP_LEVEL_V2_KEYS = {
    "schema_version", "part_name", "task_type", "units", "mesh",
    "fusion_requirements", "engineering_requirements", "export_provenance_required", "notes",
}
TOP_LEVEL_V1_KEYS = {
    "schema_version", "part_name", "units", *MESH_KEYS, "notes",
}
VALID_STATUSES = {"PASS", "FAIL", "NOT_VERIFIED", "NOT_APPLICABLE"}


def default_fusion_requirements(task_type: str = "part") -> list[dict[str, Any]]:
    requirements = [
        {"id": "active_document", "required": True, "description": "Active Fusion document and design context confirmed"},
        {"id": "safe_checkpoint", "required": True, "description": "Original design preserved by save, version, copy, or explicit checkpoint"},
        {"id": "units_confirmed", "required": True, "description": "Design units confirmed"},
        {"id": "component_structure", "required": True, "description": "Expected components and bodies verified"},
        {"id": "critical_parameters", "required": True, "description": "Critical dimensions or named parameters verified in Fusion"},
        {"id": "feature_health", "required": True, "description": "No unresolved feature or timeline failures"},
        {"id": "export_selection", "required": True, "description": "Exported body/component matches the intended final candidate"},
    ]
    if task_type == "assembly":
        requirements.extend([
            {"id": "joints_verified", "required": True, "description": "Joint type, axis, limits, and intended degrees of freedom verified"},
            {"id": "motion_sampled", "required": True, "description": "Neutral, extreme, and representative intermediate positions inspected"},
            {"id": "interference_checked", "required": True, "description": "Interference checked at representative positions"},
        ])
    return requirements


def default_engineering_requirements() -> list[dict[str, Any]]:
    return [
        {"id": "material_confirmed", "required": False, "description": "Material and manufacturing process confirmed"},
        {"id": "loads_reviewed", "required": False, "description": "Expected loads, torque, impact, and safety factors reviewed"},
        {"id": "tolerances_reviewed", "required": False, "description": "Fits, clearances, shrinkage, and manufacturing tolerances reviewed"},
        {"id": "physical_test_planned", "required": False, "description": "Physical fit/function test planned before competition or deployment"},
    ]


def default_contract(part_name: str, task_type: str = "part") -> dict[str, Any]:
    if task_type not in {"part", "assembly"}:
        raise GuardianError("task_type must be part or assembly")
    return {
        "schema_version": 2,
        "part_name": part_name,
        "task_type": task_type,
        "units": "mm",
        "mesh": {
            "expected_dimensions_mm": {
                "x": {"target": 20.0, "tolerance": 0.1},
                "y": {"target": 20.0, "tolerance": 0.1},
                "z": {"target": 10.0, "tolerance": 0.1},
            },
            "require_watertight": True,
            "max_shells": 1,
            "max_boundary_edges": 0,
            "max_nonmanifold_edges": 0,
            "max_degenerate_triangles": 0,
            "max_duplicate_triangles": 0,
            "max_inconsistent_winding_edges": 0,
            "max_sliver_triangles": 0,
            "min_triangle_quality": 0.01,
            "min_triangles": 12,
            "max_triangles": 2_000_000,
            "require_positive_signed_volume": True,
        },
        "fusion_requirements": default_fusion_requirements(task_type),
        "engineering_requirements": default_engineering_requirements(),
        "export_provenance_required": True,
        "notes": [
            "Replace example dimensions with actual acceptance criteria.",
            "Mesh checks do not verify wall thickness, joints, strength, or local feature tolerances.",
        ],
    }


def _validate_range(value: Any, name: str) -> None:
    if not isinstance(value, dict) or not value:
        raise GuardianError(f"{name} must be a non-empty object")
    allowed = {"target", "tolerance", "min", "max"}
    unknown = set(value) - allowed
    if unknown:
        raise GuardianError(f"{name} has unknown keys: {sorted(unknown)}")
    if "target" in value:
        if "tolerance" not in value or len(value) != 2:
            raise GuardianError(f"{name} target requires exactly target+tolerance")
        if float(value["tolerance"]) < 0:
            raise GuardianError(f"{name}.tolerance cannot be negative")
    elif not ({"min", "max"} & set(value)):
        raise GuardianError(f"{name} requires target+tolerance or min/max")
    for key, item in value.items():
        if not isinstance(item, (int, float)) or isinstance(item, bool):
            raise GuardianError(f"{name}.{key} must be numeric")
    if "min" in value and "max" in value and float(value["min"]) > float(value["max"]):
        raise GuardianError(f"{name}.min cannot exceed max")


def _validate_requirements(items: Any, name: str) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        raise GuardianError(f"{name} must be an array")
    seen: set[str] = set()
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise GuardianError(f"{name}[{index}] must be an object")
        unknown = set(item) - {"id", "required", "description"}
        if unknown:
            raise GuardianError(f"{name}[{index}] has unknown keys: {sorted(unknown)}")
        check_id = item.get("id")
        if not isinstance(check_id, str) or not check_id.strip():
            raise GuardianError(f"{name}[{index}].id must be a non-empty string")
        if check_id in seen:
            raise GuardianError(f"duplicate requirement id: {check_id}")
        seen.add(check_id)
        if not isinstance(item.get("required", True), bool):
            raise GuardianError(f"{name}[{index}].required must be boolean")
        if not isinstance(item.get("description", ""), str):
            raise GuardianError(f"{name}[{index}].description must be a string")
    return items


def _validate_mesh(mesh: Any) -> dict[str, Any]:
    if not isinstance(mesh, dict):
        raise GuardianError("mesh must be an object")
    unknown = set(mesh) - MESH_KEYS
    if unknown:
        raise GuardianError(f"unknown mesh fields: {sorted(unknown)}")
    dimensions = mesh.get("expected_dimensions_mm", {})
    if not isinstance(dimensions, dict) or set(dimensions) - {"x", "y", "z"}:
        raise GuardianError("expected_dimensions_mm must contain only x/y/z")
    for axis, requirement in dimensions.items():
        _validate_range(requirement, f"expected_dimensions_mm.{axis}")
    for key in ("volume_mm3", "surface_area_mm2", "mass_g"):
        if key in mesh:
            _validate_range(mesh[key], key)
    if "density_g_cm3" in mesh:
        density = mesh["density_g_cm3"]
        if not isinstance(density, (int, float)) or isinstance(density, bool) or float(density) <= 0:
            raise GuardianError("density_g_cm3 must be positive")
        if "mass_g" not in mesh:
            raise GuardianError("density_g_cm3 is only useful when mass_g is specified")
    for key in (
        "max_shells", "max_boundary_edges", "max_nonmanifold_edges",
        "max_degenerate_triangles", "max_duplicate_triangles",
        "max_inconsistent_winding_edges", "max_sliver_triangles", "min_triangles", "max_triangles",
    ):
        if key in mesh and (not isinstance(mesh[key], int) or isinstance(mesh[key], bool) or mesh[key] < 0):
            raise GuardianError(f"{key} must be a non-negative integer")
    if "min_triangle_quality" in mesh:
        quality = float(mesh["min_triangle_quality"])
        if not 0 <= quality <= 1:
            raise GuardianError("min_triangle_quality must be between 0 and 1")
    plate = mesh.get("build_plate")
    if plate is not None:
        allowed = {"axis", "plane_mm", "tolerance_mm", "min_contact_vertices", "min_contact_area_mm2"}
        if not isinstance(plate, dict) or set(plate) - allowed:
            raise GuardianError("invalid build_plate object")
        if plate.get("axis") not in {"x", "y", "z"}:
            raise GuardianError("build_plate.axis must be x, y, or z")
        if float(plate.get("tolerance_mm", 0)) < 0:
            raise GuardianError("build_plate.tolerance_mm cannot be negative")
        if int(plate.get("min_contact_vertices", 0)) < 0 or float(plate.get("min_contact_area_mm2", 0)) < 0:
            raise GuardianError("build_plate minimums cannot be negative")
    orientation = mesh.get("orientation")
    if orientation is not None:
        allowed = {"build_axis", "severe_overhang_angle_degrees", "max_severe_downward_area_mm2"}
        if not isinstance(orientation, dict) or set(orientation) - allowed:
            raise GuardianError("invalid orientation object")
        if orientation.get("build_axis", "z") not in {"x", "y", "z"}:
            raise GuardianError("orientation.build_axis must be x, y, or z")
        angle = float(orientation.get("severe_overhang_angle_degrees", 45.0))
        if not 0 <= angle <= 90:
            raise GuardianError("orientation.severe_overhang_angle_degrees must be between 0 and 90")
        if float(orientation.get("max_severe_downward_area_mm2", 0)) < 0:
            raise GuardianError("orientation.max_severe_downward_area_mm2 cannot be negative")
    return mesh


def validate_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise GuardianError("contract must be a JSON object")
    version = contract.get("schema_version", 1)
    if version == 1:
        unknown = set(contract) - TOP_LEVEL_V1_KEYS
        if unknown:
            raise GuardianError(f"unknown contract fields: {sorted(unknown)}")
        if contract.get("units", "mm") != "mm":
            raise GuardianError("STL contract units must be mm")
        _validate_mesh({key: value for key, value in contract.items() if key in MESH_KEYS})
        return contract
    if version != 2:
        raise GuardianError("supported contract schema versions are 1 and 2")
    unknown = set(contract) - TOP_LEVEL_V2_KEYS
    if unknown:
        raise GuardianError(f"unknown contract fields: {sorted(unknown)}")
    if contract.get("units", "mm") != "mm":
        raise GuardianError("contract units must be mm")
    task_type = contract.get("task_type", "part")
    if task_type not in {"part", "assembly"}:
        raise GuardianError("task_type must be part or assembly")
    _validate_mesh(contract.get("mesh", {}))
    _validate_requirements(contract.get("fusion_requirements", []), "fusion_requirements")
    _validate_requirements(contract.get("engineering_requirements", []), "engineering_requirements")
    if not isinstance(contract.get("export_provenance_required", True), bool):
        raise GuardianError("export_provenance_required must be boolean")
    return contract


def mesh_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return contract.get("mesh", {}) if contract.get("schema_version", 1) == 2 else {
        key: value for key, value in contract.items() if key in MESH_KEYS
    }


def _range_check(value: float, requirement: dict[str, Any]) -> tuple[bool, str]:
    if "target" in requirement:
        target, tolerance = float(requirement["target"]), float(requirement["tolerance"])
        return abs(value - target) <= tolerance, f"{target} ± {tolerance}"
    minimum = float(requirement.get("min", float("-inf")))
    maximum = float(requirement.get("max", float("inf")))
    return minimum <= value <= maximum, f"[{minimum}, {maximum}]"


def evaluate_contract(
    metrics: dict[str, Any], contract: dict[str, Any], triangles: list[Triangle]
) -> list[dict[str, Any]]:
    mesh = mesh_contract(contract)
    checks: list[dict[str, Any]] = []

    def add(check_id: str, passed: bool, actual: Any, expected: Any) -> None:
        checks.append({"id": check_id, "status": "PASS" if passed else "FAIL", "actual": actual, "expected": expected})

    for axis, requirement in mesh.get("expected_dimensions_mm", {}).items():
        actual = float(metrics["dimensions_mm"][axis])
        passed, expected = _range_check(actual, requirement)
        add(f"dimension_{axis}", passed, actual, expected)
    for key, metric_key in (("volume_mm3", "absolute_volume_mm3"), ("surface_area_mm2", "surface_area_mm2")):
        if key in mesh:
            actual = float(metrics[metric_key])
            passed, expected = _range_check(actual, mesh[key])
            add(key, passed, actual, expected)
    if "mass_g" in mesh:
        density = float(mesh["density_g_cm3"])
        mass = float(metrics["absolute_volume_mm3"]) / 1000.0 * density
        passed, expected = _range_check(mass, mesh["mass_g"])
        add("mass_g", passed, mass, expected)
    mappings = {
        "max_shells": "shell_count", "max_boundary_edges": "boundary_edge_count",
        "max_nonmanifold_edges": "nonmanifold_edge_count",
        "max_degenerate_triangles": "degenerate_triangle_count",
        "max_duplicate_triangles": "duplicate_triangle_count",
        "max_inconsistent_winding_edges": "inconsistent_winding_edge_count",
        "max_sliver_triangles": "sliver_triangle_count", "max_triangles": "triangle_count",
    }
    for contract_key, metric_key in mappings.items():
        if contract_key in mesh:
            add(contract_key, metrics[metric_key] <= mesh[contract_key], metrics[metric_key], f"<= {mesh[contract_key]}")
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
        contact = build_plate_contact(
            triangles, plate["axis"], float(plate.get("plane_mm", 0.0)), float(plate.get("tolerance_mm", 0.05))
        )
        minimum_vertices = int(plate.get("min_contact_vertices", 0))
        minimum_area = float(plate.get("min_contact_area_mm2", 0))
        if "min_contact_vertices" in plate:
            add("build_plate_contact_vertices", contact["vertex_count"] >= minimum_vertices, contact["vertex_count"], f">= {minimum_vertices}")
        if "min_contact_area_mm2" in plate:
            add("build_plate_contact_area", contact["area_mm2"] >= minimum_area, contact["area_mm2"], f">= {minimum_area}")
    if "orientation" in mesh and "max_severe_downward_area_mm2" in mesh["orientation"]:
        actual = metrics["severe_downward_area"]["area_mm2"]
        maximum = float(mesh["orientation"]["max_severe_downward_area_mm2"])
        add("max_severe_downward_area_mm2", actual <= maximum, actual, f"<= {maximum}")
    return checks
