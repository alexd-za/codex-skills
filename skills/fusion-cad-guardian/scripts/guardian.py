#!/usr/bin/env python3
"""Fusion CAD Guardian: dependency-free STL audit and regression tooling.

The script intentionally operates outside Autodesk Fusion. It complements a
Fusion MCP workflow by providing deterministic checks on exported STL meshes.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
from typing import Any, Iterable, Sequence

VERSION = "1.0.0"
SUPPORTED_CONTRACT_KEYS = {
    "schema_version",
    "part_name",
    "units",
    "expected_dimensions_mm",
    "volume_mm3",
    "surface_area_mm2",
    "require_watertight",
    "max_shells",
    "max_boundary_edges",
    "max_nonmanifold_edges",
    "max_degenerate_triangles",
    "max_duplicate_triangles",
    "max_inconsistent_winding_edges",
    "min_triangles",
    "max_triangles",
    "require_positive_signed_volume",
    "build_plate",
    "notes",
}
AXIS_INDEX = {"x": 0, "y": 1, "z": 2}
LIMITATIONS = [
    "STL analysis does not verify assembly joints, motion, interference, or component connectivity.",
    "STL analysis does not verify minimum wall thickness, structural strength, material suitability, or print shrinkage.",
    "Bounding-box dimensions do not verify internal hole positions, local clearances, or feature tolerances.",
    "Results depend on the exported tessellation and on the STL matching the intended final Fusion body or component.",
]

Vec3 = tuple[float, float, float]
Triangle = tuple[Vec3, Vec3, Vec3]


class GuardianError(Exception):
    """Expected input or validation error."""


def _utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sub(a: Vec3, b: Vec3) -> Vec3:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Vec3, b: Vec3) -> Vec3:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def _dot(a: Vec3, b: Vec3) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _norm(a: Vec3) -> float:
    return math.sqrt(_dot(a, a))


def _finite_vertex(vertex: Vec3) -> bool:
    return all(math.isfinite(value) for value in vertex)


def _detect_and_read_stl(path: Path) -> tuple[str, list[Triangle]]:
    if not path.is_file():
        raise GuardianError(f"STL file not found: {path}")
    size = path.stat().st_size
    if size < 15:
        raise GuardianError(f"STL file is too small to be valid: {path}")

    with path.open("rb") as handle:
        header = handle.read(84)

    if len(header) >= 84:
        count = struct.unpack_from("<I", header, 80)[0]
        expected = 84 + count * 50
        # Exact length is preferred. A small amount of trailing data is tolerated.
        if count > 0 and expected <= size and size - expected <= 1024:
            return "binary", _read_binary_stl(path, count)

    try:
        return "ascii", _read_ascii_stl(path)
    except UnicodeDecodeError as exc:
        raise GuardianError(
            "File does not match a valid binary STL layout and cannot be decoded as ASCII STL"
        ) from exc


def _read_binary_stl(path: Path, count: int) -> list[Triangle]:
    triangles: list[Triangle] = []
    with path.open("rb") as handle:
        handle.seek(84)
        for index in range(count):
            record = handle.read(50)
            if len(record) != 50:
                raise GuardianError(f"Binary STL ended early at triangle {index}")
            values = struct.unpack("<12fH", record)
            vertices = (
                (float(values[3]), float(values[4]), float(values[5])),
                (float(values[6]), float(values[7]), float(values[8])),
                (float(values[9]), float(values[10]), float(values[11])),
            )
            if not all(_finite_vertex(vertex) for vertex in vertices):
                raise GuardianError(f"Triangle {index} contains NaN or infinite coordinates")
            triangles.append(vertices)
    if not triangles:
        raise GuardianError("STL contains no triangles")
    return triangles


def _read_ascii_stl(path: Path) -> list[Triangle]:
    vertices: list[Vec3] = []
    with path.open("r", encoding="utf-8-sig", errors="strict") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped.lower().startswith("vertex "):
                continue
            parts = stripped.split()
            if len(parts) != 4:
                raise GuardianError(f"Malformed vertex line at {line_number}: {stripped}")
            try:
                vertex = (float(parts[1]), float(parts[2]), float(parts[3]))
            except ValueError as exc:
                raise GuardianError(f"Invalid numeric vertex at line {line_number}") from exc
            if not _finite_vertex(vertex):
                raise GuardianError(f"Vertex at line {line_number} contains NaN or infinity")
            vertices.append(vertex)
    if not vertices:
        raise GuardianError("ASCII STL contains no vertex records")
    if len(vertices) % 3 != 0:
        raise GuardianError(
            f"ASCII STL has {len(vertices)} vertices, which is not divisible by three"
        )
    triangles = [
        (vertices[index], vertices[index + 1], vertices[index + 2])
        for index in range(0, len(vertices), 3)
    ]
    return triangles


class _DisjointSet:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def union(self, left: int, right: int) -> None:
        root_left = self.find(left)
        root_right = self.find(right)
        if root_left == root_right:
            return
        if self.rank[root_left] < self.rank[root_right]:
            root_left, root_right = root_right, root_left
        self.parent[root_right] = root_left
        if self.rank[root_left] == self.rank[root_right]:
            self.rank[root_left] += 1


def _quantize(vertex: Vec3, tolerance: float) -> tuple[int, int, int]:
    return (
        int(round(vertex[0] / tolerance)),
        int(round(vertex[1] / tolerance)),
        int(round(vertex[2] / tolerance)),
    )


def analyze_mesh(
    triangles: Sequence[Triangle],
    *,
    weld_tolerance_mm: float = 1e-6,
    area_epsilon_mm2: float = 1e-12,
) -> dict[str, Any]:
    if weld_tolerance_mm <= 0:
        raise GuardianError("weld tolerance must be greater than zero")
    if area_epsilon_mm2 < 0:
        raise GuardianError("area epsilon cannot be negative")
    if not triangles:
        raise GuardianError("mesh contains no triangles")

    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    unique_vertices: set[tuple[int, int, int]] = set()
    edge_records: dict[
        tuple[tuple[int, int, int], tuple[int, int, int]], dict[str, Any]
    ] = {}
    duplicate_keys: dict[tuple[tuple[int, int, int], ...], int] = {}
    dsu = _DisjointSet(len(triangles))

    surface_area = 0.0
    signed_volume = 0.0
    degenerate = 0

    for triangle_index, triangle in enumerate(triangles):
        keys = [_quantize(vertex, weld_tolerance_mm) for vertex in triangle]
        for vertex, key in zip(triangle, keys):
            unique_vertices.add(key)
            for axis in range(3):
                mins[axis] = min(mins[axis], vertex[axis])
                maxs[axis] = max(maxs[axis], vertex[axis])

        ab = _sub(triangle[1], triangle[0])
        ac = _sub(triangle[2], triangle[0])
        cross = _cross(ab, ac)
        area = 0.5 * _norm(cross)
        surface_area += area
        if area <= area_epsilon_mm2:
            degenerate += 1
        signed_volume += _dot(triangle[0], _cross(triangle[1], triangle[2])) / 6.0

        triangle_key = tuple(sorted(keys))
        duplicate_keys[triangle_key] = duplicate_keys.get(triangle_key, 0) + 1

        for start, end in ((keys[0], keys[1]), (keys[1], keys[2]), (keys[2], keys[0])):
            if start <= end:
                edge_key = (start, end)
                direction = 1
            else:
                edge_key = (end, start)
                direction = -1
            record = edge_records.setdefault(
                edge_key, {"count": 0, "direction_sum": 0, "triangles": []}
            )
            record["count"] += 1
            record["direction_sum"] += direction
            record["triangles"].append(triangle_index)

    boundary_edges = 0
    nonmanifold_edges = 0
    inconsistent_winding_edges = 0
    manifold_edges = 0

    for record in edge_records.values():
        count = int(record["count"])
        if count == 1:
            boundary_edges += 1
        elif count == 2:
            manifold_edges += 1
            if abs(int(record["direction_sum"])) == 2:
                inconsistent_winding_edges += 1
        else:
            nonmanifold_edges += 1

        connected = record["triangles"]
        if len(connected) > 1:
            first = connected[0]
            for other in connected[1:]:
                dsu.union(first, other)

    shells = len({dsu.find(index) for index in range(len(triangles))})
    duplicates = sum(count - 1 for count in duplicate_keys.values() if count > 1)
    dimensions = [maxs[axis] - mins[axis] for axis in range(3)]
    watertight = boundary_edges == 0 and nonmanifold_edges == 0 and degenerate == 0

    return {
        "triangle_count": len(triangles),
        "unique_vertex_count": len(unique_vertices),
        "edge_count": len(edge_records),
        "manifold_edge_count": manifold_edges,
        "boundary_edge_count": boundary_edges,
        "nonmanifold_edge_count": nonmanifold_edges,
        "inconsistent_winding_edge_count": inconsistent_winding_edges,
        "degenerate_triangle_count": degenerate,
        "duplicate_triangle_count": duplicates,
        "shell_count": shells,
        "watertight": watertight,
        "bbox_min_mm": {"x": mins[0], "y": mins[1], "z": mins[2]},
        "bbox_max_mm": {"x": maxs[0], "y": maxs[1], "z": maxs[2]},
        "dimensions_mm": {"x": dimensions[0], "y": dimensions[1], "z": dimensions[2]},
        "surface_area_mm2": surface_area,
        "signed_volume_mm3": signed_volume,
        "absolute_volume_mm3": abs(signed_volume),
        "weld_tolerance_mm": weld_tolerance_mm,
        "area_epsilon_mm2": area_epsilon_mm2,
    }


def _load_json(path: Path) -> Any:
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        raise GuardianError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise GuardianError(f"Invalid JSON in {path}: {exc}") from exc


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def validate_contract(contract: Any) -> dict[str, Any]:
    if not isinstance(contract, dict):
        raise GuardianError("contract root must be a JSON object")

    unknown = sorted(set(contract) - SUPPORTED_CONTRACT_KEYS)
    if unknown:
        raise GuardianError(f"unsupported contract field(s): {', '.join(unknown)}")

    version = contract.get("schema_version", 1)
    if version != 1:
        raise GuardianError(f"unsupported schema_version: {version!r}; expected 1")

    units = contract.get("units", "mm")
    if units != "mm":
        raise GuardianError("the current auditor supports only millimetres (units='mm')")

    dimensions = contract.get("expected_dimensions_mm", {})
    if not isinstance(dimensions, dict):
        raise GuardianError("expected_dimensions_mm must be an object")
    for axis, spec in dimensions.items():
        if axis not in AXIS_INDEX:
            raise GuardianError(f"unsupported dimension axis: {axis!r}")
        _normalize_range(spec, f"expected_dimensions_mm.{axis}")

    for field in ("volume_mm3", "surface_area_mm2"):
        if field in contract:
            _normalize_range(contract[field], field)

    for field in (
        "max_shells",
        "max_boundary_edges",
        "max_nonmanifold_edges",
        "max_degenerate_triangles",
        "max_duplicate_triangles",
        "max_inconsistent_winding_edges",
        "min_triangles",
        "max_triangles",
    ):
        if field in contract:
            value = contract[field]
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise GuardianError(f"{field} must be a non-negative integer")

    for field in ("require_watertight", "require_positive_signed_volume"):
        if field in contract and not isinstance(contract[field], bool):
            raise GuardianError(f"{field} must be true or false")

    build_plate = contract.get("build_plate")
    if build_plate is not None:
        if not isinstance(build_plate, dict):
            raise GuardianError("build_plate must be an object")
        allowed = {"axis", "plane_mm", "tolerance_mm", "min_contact_vertices"}
        unknown_bp = sorted(set(build_plate) - allowed)
        if unknown_bp:
            raise GuardianError(
                f"unsupported build_plate field(s): {', '.join(unknown_bp)}"
            )
        axis = build_plate.get("axis", "z")
        if axis not in AXIS_INDEX:
            raise GuardianError("build_plate.axis must be x, y, or z")
        for field in ("plane_mm", "tolerance_mm"):
            value = build_plate.get(field, 0.0 if field == "plane_mm" else 0.05)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise GuardianError(f"build_plate.{field} must be numeric")
            if field == "tolerance_mm" and value < 0:
                raise GuardianError("build_plate.tolerance_mm cannot be negative")
        contacts = build_plate.get("min_contact_vertices", 3)
        if isinstance(contacts, bool) or not isinstance(contacts, int) or contacts < 0:
            raise GuardianError("build_plate.min_contact_vertices must be non-negative integer")

    notes = contract.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(item, str) for item in notes):
        raise GuardianError("notes must be an array of strings")

    return contract


def _normalize_range(spec: Any, field: str) -> tuple[float | None, float | None, str]:
    if isinstance(spec, bool):
        raise GuardianError(f"{field} must be a numeric range object")
    if isinstance(spec, (int, float)):
        value = float(spec)
        if not math.isfinite(value):
            raise GuardianError(f"{field} contains a non-finite value")
        return value, value, f"exactly {value:g}"
    if not isinstance(spec, dict):
        raise GuardianError(f"{field} must be numeric or an object")
    allowed = {"target", "tolerance", "min", "max"}
    unknown = sorted(set(spec) - allowed)
    if unknown:
        raise GuardianError(f"{field} has unsupported keys: {', '.join(unknown)}")

    if "target" in spec:
        if "min" in spec or "max" in spec:
            raise GuardianError(f"{field} cannot mix target with min/max")
        target = _finite_number(spec["target"], f"{field}.target")
        tolerance = _finite_number(spec.get("tolerance", 0.0), f"{field}.tolerance")
        if tolerance < 0:
            raise GuardianError(f"{field}.tolerance cannot be negative")
        minimum, maximum = target - tolerance, target + tolerance
        return minimum, maximum, f"{target:g} ± {tolerance:g}"

    if "tolerance" in spec:
        raise GuardianError(f"{field}.tolerance requires target")
    minimum = _finite_number(spec["min"], f"{field}.min") if "min" in spec else None
    maximum = _finite_number(spec["max"], f"{field}.max") if "max" in spec else None
    if minimum is None and maximum is None:
        raise GuardianError(f"{field} requires target or min/max")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise GuardianError(f"{field}.min cannot exceed max")
    if minimum is None:
        label = f"≤ {maximum:g}"
    elif maximum is None:
        label = f"≥ {minimum:g}"
    else:
        label = f"{minimum:g} to {maximum:g}"
    return minimum, maximum, label


def _finite_number(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GuardianError(f"{field} must be numeric")
    result = float(value)
    if not math.isfinite(result):
        raise GuardianError(f"{field} must be finite")
    return result


def _in_range(actual: float, minimum: float | None, maximum: float | None) -> bool:
    return (minimum is None or actual >= minimum) and (
        maximum is None or actual <= maximum
    )


def _format_number(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        return f"{value:.9g}"
    return str(value)


def evaluate_contract(
    metrics: dict[str, Any], contract: dict[str, Any], triangles: Sequence[Triangle]
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []

    def add(
        check_id: str,
        passed: bool,
        actual: Any,
        expected: Any,
        message: str,
    ) -> None:
        checks.append(
            {
                "id": check_id,
                "status": "PASS" if passed else "FAIL",
                "actual": actual,
                "expected": expected,
                "message": message,
            }
        )

    for axis, spec in contract.get("expected_dimensions_mm", {}).items():
        minimum, maximum, label = _normalize_range(
            spec, f"expected_dimensions_mm.{axis}"
        )
        actual = float(metrics["dimensions_mm"][axis])
        passed = _in_range(actual, minimum, maximum)
        add(
            f"dimension_{axis}",
            passed,
            actual,
            label,
            f"{axis.upper()} bounding-box dimension is {_format_number(actual)} mm",
        )

    for field, metric_key, unit in (
        ("volume_mm3", "absolute_volume_mm3", "mm³"),
        ("surface_area_mm2", "surface_area_mm2", "mm²"),
    ):
        if field in contract:
            minimum, maximum, label = _normalize_range(contract[field], field)
            actual = float(metrics[metric_key])
            add(
                field,
                _in_range(actual, minimum, maximum),
                actual,
                label,
                f"Measured {field} is {_format_number(actual)} {unit}",
            )

    direct_max = {
        "max_shells": "shell_count",
        "max_boundary_edges": "boundary_edge_count",
        "max_nonmanifold_edges": "nonmanifold_edge_count",
        "max_degenerate_triangles": "degenerate_triangle_count",
        "max_duplicate_triangles": "duplicate_triangle_count",
        "max_inconsistent_winding_edges": "inconsistent_winding_edge_count",
        "max_triangles": "triangle_count",
    }
    for contract_key, metric_key in direct_max.items():
        if contract_key in contract:
            limit = int(contract[contract_key])
            actual = int(metrics[metric_key])
            add(
                contract_key,
                actual <= limit,
                actual,
                f"≤ {limit}",
                f"{metric_key} is {actual}",
            )

    if "min_triangles" in contract:
        limit = int(contract["min_triangles"])
        actual = int(metrics["triangle_count"])
        add(
            "min_triangles",
            actual >= limit,
            actual,
            f"≥ {limit}",
            f"triangle_count is {actual}",
        )

    if contract.get("require_watertight") is True:
        actual = bool(metrics["watertight"])
        add(
            "require_watertight",
            actual,
            actual,
            True,
            "Mesh is watertight" if actual else "Mesh is not watertight",
        )

    if contract.get("require_positive_signed_volume") is True:
        actual = float(metrics["signed_volume_mm3"])
        add(
            "require_positive_signed_volume",
            actual > 0,
            actual,
            "> 0",
            "Positive signed volume suggests outward global orientation",
        )

    build_plate = contract.get("build_plate")
    if build_plate is not None:
        axis = str(build_plate.get("axis", "z"))
        axis_index = AXIS_INDEX[axis]
        plane = float(build_plate.get("plane_mm", 0.0))
        tolerance = float(build_plate.get("tolerance_mm", 0.05))
        minimum_contacts = int(build_plate.get("min_contact_vertices", 3))
        quantization = float(metrics["weld_tolerance_mm"])
        contacts: set[tuple[int, int, int]] = set()
        minimum_axis = math.inf
        for triangle in triangles:
            for vertex in triangle:
                minimum_axis = min(minimum_axis, vertex[axis_index])
                if abs(vertex[axis_index] - plane) <= tolerance:
                    contacts.add(_quantize(vertex, quantization))
        add(
            "build_plate_minimum",
            abs(minimum_axis - plane) <= tolerance,
            minimum_axis,
            f"{plane:g} ± {tolerance:g} mm on {axis.upper()}",
            f"Minimum {axis.upper()} coordinate is {_format_number(minimum_axis)} mm",
        )
        add(
            "build_plate_contact_vertices",
            len(contacts) >= minimum_contacts,
            len(contacts),
            f"≥ {minimum_contacts}",
            f"Unique vertices within build-plane tolerance: {len(contacts)}",
        )

    return checks


def audit_stl(
    mesh_path: Path,
    *,
    contract_path: Path | None = None,
    weld_tolerance_mm: float = 1e-6,
    area_epsilon_mm2: float = 1e-12,
) -> dict[str, Any]:
    stl_format, triangles = _detect_and_read_stl(mesh_path)
    metrics = analyze_mesh(
        triangles,
        weld_tolerance_mm=weld_tolerance_mm,
        area_epsilon_mm2=area_epsilon_mm2,
    )

    contract: dict[str, Any] | None = None
    checks: list[dict[str, Any]] = []
    if contract_path is not None:
        contract = validate_contract(_load_json(contract_path))
        checks = evaluate_contract(metrics, contract, triangles)
        verdict = "PASS" if all(check["status"] == "PASS" for check in checks) else "FAIL"
    else:
        verdict = "AUDIT_ONLY"

    return {
        "guardian_version": VERSION,
        "generated_at": _utc_now(),
        "mesh": {
            "path": str(mesh_path.resolve()),
            "name": mesh_path.name,
            "bytes": mesh_path.stat().st_size,
            "sha256": _sha256(mesh_path),
            "stl_format": stl_format,
        },
        "contract_path": str(contract_path.resolve()) if contract_path else None,
        "contract": contract,
        "metrics": metrics,
        "checks": checks,
        "verdict": verdict,
        "limitations": LIMITATIONS,
    }


def render_audit_markdown(report: dict[str, Any]) -> str:
    mesh = report["mesh"]
    metrics = report["metrics"]
    lines = [
        "# Fusion CAD Guardian mesh report",
        "",
        f"- **Verdict:** `{report['verdict']}`",
        f"- **Mesh:** `{mesh['name']}`",
        f"- **Format:** `{mesh['stl_format']}`",
        f"- **SHA-256:** `{mesh['sha256']}`",
        f"- **Generated:** `{report['generated_at']}`",
        "",
        "## Geometry metrics",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Dimensions X × Y × Z | {_format_number(metrics['dimensions_mm']['x'])} × {_format_number(metrics['dimensions_mm']['y'])} × {_format_number(metrics['dimensions_mm']['z'])} mm |",
        f"| Bounding-box minimum | X {_format_number(metrics['bbox_min_mm']['x'])}, Y {_format_number(metrics['bbox_min_mm']['y'])}, Z {_format_number(metrics['bbox_min_mm']['z'])} mm |",
        f"| Bounding-box maximum | X {_format_number(metrics['bbox_max_mm']['x'])}, Y {_format_number(metrics['bbox_max_mm']['y'])}, Z {_format_number(metrics['bbox_max_mm']['z'])} mm |",
        f"| Triangles | {metrics['triangle_count']} |",
        f"| Unique vertices | {metrics['unique_vertex_count']} |",
        f"| Edge-connected shells | {metrics['shell_count']} |",
        f"| Boundary edges | {metrics['boundary_edge_count']} |",
        f"| Non-manifold edges | {metrics['nonmanifold_edge_count']} |",
        f"| Inconsistent winding edges | {metrics['inconsistent_winding_edge_count']} |",
        f"| Degenerate triangles | {metrics['degenerate_triangle_count']} |",
        f"| Duplicate triangles | {metrics['duplicate_triangle_count']} |",
        f"| Watertight | {metrics['watertight']} |",
        f"| Surface area | {_format_number(metrics['surface_area_mm2'])} mm² |",
        f"| Signed volume | {_format_number(metrics['signed_volume_mm3'])} mm³ |",
        f"| Absolute volume | {_format_number(metrics['absolute_volume_mm3'])} mm³ |",
        "",
    ]

    if report["checks"]:
        lines.extend(
            [
                "## Contract checks",
                "",
                "| Status | Requirement | Actual | Expected |",
                "|---|---|---:|---:|",
            ]
        )
        for check in report["checks"]:
            lines.append(
                f"| **{check['status']}** | `{check['id']}` | {_format_number(check['actual'])} | {_format_number(check['expected'])} |"
            )
        lines.append("")
    else:
        lines.extend(
            [
                "## Contract checks",
                "",
                "No contract was supplied. Metrics were collected without an acceptance verdict.",
                "",
            ]
        )

    lines.extend(["## Limitations", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    lines.append("")
    return "\n".join(lines)


def _safe_delta(after: Any, before: Any) -> float | None:
    if isinstance(after, bool) or isinstance(before, bool):
        return None
    if isinstance(after, (int, float)) and isinstance(before, (int, float)):
        return float(after) - float(before)
    return None


def compare_reports(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    for name, report in (("before", before), ("after", after)):
        if not isinstance(report, dict) or "metrics" not in report or "verdict" not in report:
            raise GuardianError(f"{name} file is not a Guardian audit report")

    before_metrics = before["metrics"]
    after_metrics = after["metrics"]
    metric_keys = [
        "triangle_count",
        "unique_vertex_count",
        "shell_count",
        "boundary_edge_count",
        "nonmanifold_edge_count",
        "inconsistent_winding_edge_count",
        "degenerate_triangle_count",
        "duplicate_triangle_count",
        "surface_area_mm2",
        "signed_volume_mm3",
        "absolute_volume_mm3",
    ]
    metric_deltas: dict[str, Any] = {}
    for key in metric_keys:
        metric_deltas[key] = {
            "before": before_metrics.get(key),
            "after": after_metrics.get(key),
            "delta": _safe_delta(after_metrics.get(key), before_metrics.get(key)),
        }

    dimension_deltas: dict[str, Any] = {}
    for axis in ("x", "y", "z"):
        old = before_metrics["dimensions_mm"][axis]
        new = after_metrics["dimensions_mm"][axis]
        dimension_deltas[axis] = {
            "before": old,
            "after": new,
            "delta": float(new) - float(old),
        }

    regressions: list[str] = []
    defect_metrics = [
        "boundary_edge_count",
        "nonmanifold_edge_count",
        "inconsistent_winding_edge_count",
        "degenerate_triangle_count",
        "duplicate_triangle_count",
        "shell_count",
    ]
    for key in defect_metrics:
        old = float(before_metrics.get(key, 0))
        new = float(after_metrics.get(key, 0))
        if new > old:
            regressions.append(f"{key} increased from {_format_number(old)} to {_format_number(new)}")

    if before.get("verdict") == "PASS" and after.get("verdict") != "PASS":
        regressions.append(
            f"contract verdict regressed from PASS to {after.get('verdict')}"
        )
    if bool(before_metrics.get("watertight")) and not bool(after_metrics.get("watertight")):
        regressions.append("mesh regressed from watertight to not watertight")

    return {
        "guardian_version": VERSION,
        "generated_at": _utc_now(),
        "before": {
            "mesh": before.get("mesh"),
            "verdict": before.get("verdict"),
        },
        "after": {
            "mesh": after.get("mesh"),
            "verdict": after.get("verdict"),
        },
        "metric_deltas": metric_deltas,
        "dimension_deltas_mm": dimension_deltas,
        "regressions": regressions,
        "comparison_verdict": "REGRESSION" if regressions else "NO_AUTOMATIC_REGRESSION",
        "limitations": [
            "A change without an automatic regression is not necessarily an engineering improvement.",
            "Dimension and volume changes may be intentional; compare them with the design contract.",
        ],
    }


def render_compare_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# Fusion CAD Guardian regression report",
        "",
        f"- **Comparison verdict:** `{comparison['comparison_verdict']}`",
        f"- **Before contract verdict:** `{comparison['before']['verdict']}`",
        f"- **After contract verdict:** `{comparison['after']['verdict']}`",
        f"- **Generated:** `{comparison['generated_at']}`",
        "",
        "## Dimension changes",
        "",
        "| Axis | Before (mm) | After (mm) | Delta (mm) |",
        "|---|---:|---:|---:|",
    ]
    for axis in ("x", "y", "z"):
        data = comparison["dimension_deltas_mm"][axis]
        lines.append(
            f"| {axis.upper()} | {_format_number(data['before'])} | {_format_number(data['after'])} | {_format_number(data['delta'])} |"
        )

    lines.extend(
        [
            "",
            "## Metric changes",
            "",
            "| Metric | Before | After | Delta |",
            "|---|---:|---:|---:|",
        ]
    )
    for key, data in comparison["metric_deltas"].items():
        lines.append(
            f"| `{key}` | {_format_number(data['before'])} | {_format_number(data['after'])} | {_format_number(data['delta'])} |"
        )

    lines.extend(["", "## Automatic regressions", ""])
    if comparison["regressions"]:
        lines.extend(f"- **REGRESSION:** {item}" for item in comparison["regressions"])
    else:
        lines.append("- No automatic topology or contract regression was detected.")

    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in comparison["limitations"])
    lines.append("")
    return "\n".join(lines)


def _default_contract(part_name: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "part_name": part_name,
        "units": "mm",
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
        "min_triangles": 12,
        "max_triangles": 2_000_000,
        "require_positive_signed_volume": True,
        "build_plate": {
            "axis": "z",
            "plane_mm": 0.0,
            "tolerance_mm": 0.05,
            "min_contact_vertices": 3,
        },
        "notes": [
            "Replace example dimensions with real acceptance criteria.",
            "Mesh checks do not verify wall thickness or mechanical strength.",
        ],
    }


def _cube_triangles(size: float = 10.0) -> list[Triangle]:
    v000 = (0.0, 0.0, 0.0)
    v100 = (size, 0.0, 0.0)
    v110 = (size, size, 0.0)
    v010 = (0.0, size, 0.0)
    v001 = (0.0, 0.0, size)
    v101 = (size, 0.0, size)
    v111 = (size, size, size)
    v011 = (0.0, size, size)
    return [
        (v000, v110, v100),
        (v000, v010, v110),
        (v001, v101, v111),
        (v001, v111, v011),
        (v000, v100, v101),
        (v000, v101, v001),
        (v010, v111, v110),
        (v010, v011, v111),
        (v000, v001, v011),
        (v000, v011, v010),
        (v100, v110, v111),
        (v100, v111, v101),
    ]


def _write_binary_stl(path: Path, triangles: Iterable[Triangle]) -> None:
    triangle_list = list(triangles)
    header = b"Fusion CAD Guardian self-test"[:80].ljust(80, b"\0")
    with path.open("wb") as handle:
        handle.write(header)
        handle.write(struct.pack("<I", len(triangle_list)))
        for triangle in triangle_list:
            ab = _sub(triangle[1], triangle[0])
            ac = _sub(triangle[2], triangle[0])
            cross = _cross(ab, ac)
            length = _norm(cross)
            normal = (0.0, 0.0, 0.0) if length == 0 else tuple(value / length for value in cross)
            values = (
                normal[0],
                normal[1],
                normal[2],
                triangle[0][0],
                triangle[0][1],
                triangle[0][2],
                triangle[1][0],
                triangle[1][1],
                triangle[1][2],
                triangle[2][0],
                triangle[2][1],
                triangle[2][2],
                0,
            )
            handle.write(struct.pack("<12fH", *values))


def run_self_test() -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="fusion-guardian-") as temp_dir:
        temp = Path(temp_dir)
        cube_path = temp / "cube.stl"
        _write_binary_stl(cube_path, _cube_triangles(10.0))
        cube_report = audit_stl(cube_path)
        cube = cube_report["metrics"]
        cube_pass = (
            cube["triangle_count"] == 12
            and cube["shell_count"] == 1
            and cube["boundary_edge_count"] == 0
            and cube["nonmanifold_edge_count"] == 0
            and cube["watertight"] is True
            and all(abs(cube["dimensions_mm"][axis] - 10.0) < 1e-9 for axis in ("x", "y", "z"))
            and abs(cube["absolute_volume_mm3"] - 1000.0) < 1e-6
        )
        results.append({"name": "closed_cube", "passed": cube_pass, "metrics": cube})

        open_path = temp / "open.stl"
        _write_binary_stl(
            open_path,
            [((0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0))],
        )
        open_report = audit_stl(open_path)
        opened = open_report["metrics"]
        open_pass = (
            opened["triangle_count"] == 1
            and opened["boundary_edge_count"] == 3
            and opened["watertight"] is False
        )
        results.append({"name": "open_triangle", "passed": open_pass, "metrics": opened})

        contract_path = temp / "contract.json"
        contract = _default_contract("Self-test cube")
        contract["expected_dimensions_mm"] = {
            axis: {"target": 10.0, "tolerance": 0.001} for axis in ("x", "y", "z")
        }
        _write_json(contract_path, contract)
        contract_report = audit_stl(cube_path, contract_path=contract_path)
        contract_pass = contract_report["verdict"] == "PASS"
        results.append(
            {
                "name": "contract_pass",
                "passed": contract_pass,
                "verdict": contract_report["verdict"],
            }
        )

    return {
        "guardian_version": VERSION,
        "generated_at": _utc_now(),
        "passed": all(result["passed"] for result in results),
        "tests": results,
    }


def _cmd_init(args: argparse.Namespace) -> int:
    output = Path(args.out)
    if output.exists() and not args.force:
        raise GuardianError(f"output already exists: {output}; use --force to replace it")
    _write_json(output, _default_contract(args.part_name))
    print(f"Created contract template: {output}")
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    report = audit_stl(
        Path(args.mesh),
        contract_path=Path(args.contract) if args.contract else None,
        weld_tolerance_mm=args.weld_tolerance,
        area_epsilon_mm2=args.area_epsilon,
    )
    if args.json_out:
        _write_json(Path(args.json_out), report)
    if args.markdown:
        _write_text(Path(args.markdown), render_audit_markdown(report))
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 1 if report["verdict"] == "FAIL" else 0


def _cmd_compare(args: argparse.Namespace) -> int:
    comparison = compare_reports(_load_json(Path(args.before)), _load_json(Path(args.after)))
    if args.json_out:
        _write_json(Path(args.json_out), comparison)
    if args.markdown:
        _write_text(Path(args.markdown), render_compare_markdown(comparison))
    print(json.dumps(comparison, indent=2, ensure_ascii=False))
    return 1 if comparison["comparison_verdict"] == "REGRESSION" else 0


def _cmd_batch(args: argparse.Namespace) -> int:
    manifest_path = Path(args.manifest)
    manifest = _load_json(manifest_path)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("jobs"), list):
        raise GuardianError("batch manifest must be an object containing a jobs array")
    output_dir = Path(args.out_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    base = manifest_path.resolve().parent
    summaries: list[dict[str, Any]] = []
    had_failure = False
    for index, job in enumerate(manifest["jobs"]):
        if not isinstance(job, dict) or "mesh" not in job:
            raise GuardianError(f"batch job {index} must be an object containing mesh")
        name = str(job.get("name") or Path(str(job["mesh"])).stem)
        mesh_path = Path(str(job["mesh"]))
        if not mesh_path.is_absolute():
            mesh_path = base / mesh_path
        contract_path: Path | None = None
        if job.get("contract"):
            contract_path = Path(str(job["contract"]))
            if not contract_path.is_absolute():
                contract_path = base / contract_path
        report = audit_stl(
            mesh_path,
            contract_path=contract_path,
            weld_tolerance_mm=args.weld_tolerance,
            area_epsilon_mm2=args.area_epsilon,
        )
        safe_name = "".join(character if character.isalnum() or character in "-_" else "_" for character in name)
        json_path = output_dir / f"{safe_name}.mesh-report.json"
        markdown_path = output_dir / f"{safe_name}.mesh-report.md"
        _write_json(json_path, report)
        _write_text(markdown_path, render_audit_markdown(report))
        summaries.append(
            {
                "name": name,
                "mesh": str(mesh_path),
                "verdict": report["verdict"],
                "json_report": str(json_path),
                "markdown_report": str(markdown_path),
            }
        )
        if report["verdict"] == "FAIL":
            had_failure = True

    batch_report = {
        "guardian_version": VERSION,
        "generated_at": _utc_now(),
        "manifest": str(manifest_path.resolve()),
        "jobs": summaries,
        "verdict": "FAIL" if had_failure else "PASS",
    }
    _write_json(output_dir / "batch-summary.json", batch_report)
    print(json.dumps(batch_report, indent=2, ensure_ascii=False))
    return 1 if had_failure else 0


def _cmd_self_test(_args: argparse.Namespace) -> int:
    result = run_self_test()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["passed"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Deterministic STL verification for Autodesk Fusion MCP workflows"
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create a contract template")
    init_parser.add_argument("--out", required=True, help="output contract JSON path")
    init_parser.add_argument("--part-name", default="Example Part")
    init_parser.add_argument("--force", action="store_true", help="replace an existing file")
    init_parser.set_defaults(func=_cmd_init)

    audit_parser = subparsers.add_parser("audit", help="audit an ASCII or binary STL")
    audit_parser.add_argument("mesh", help="STL path")
    audit_parser.add_argument("--contract", help="optional design contract JSON")
    audit_parser.add_argument("--json", dest="json_out", help="write full JSON report")
    audit_parser.add_argument("--markdown", help="write Markdown report")
    audit_parser.add_argument(
        "--weld-tolerance",
        type=float,
        default=1e-6,
        help="vertex welding tolerance in millimetres (default: 1e-6)",
    )
    audit_parser.add_argument(
        "--area-epsilon",
        type=float,
        default=1e-12,
        help="triangle area threshold in square millimetres (default: 1e-12)",
    )
    audit_parser.set_defaults(func=_cmd_audit)

    compare_parser = subparsers.add_parser("compare", help="compare two audit JSON reports")
    compare_parser.add_argument("before", help="before JSON report")
    compare_parser.add_argument("after", help="after JSON report")
    compare_parser.add_argument("--json", dest="json_out", help="write comparison JSON")
    compare_parser.add_argument("--markdown", help="write comparison Markdown")
    compare_parser.set_defaults(func=_cmd_compare)

    batch_parser = subparsers.add_parser("batch", help="audit jobs from a batch manifest")
    batch_parser.add_argument("manifest", help="batch manifest JSON")
    batch_parser.add_argument("--out-dir", required=True, help="report output directory")
    batch_parser.add_argument("--weld-tolerance", type=float, default=1e-6)
    batch_parser.add_argument("--area-epsilon", type=float, default=1e-12)
    batch_parser.set_defaults(func=_cmd_batch)

    self_test_parser = subparsers.add_parser("self-test", help="run built-in validation tests")
    self_test_parser.set_defaults(func=_cmd_self_test)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except GuardianError as exc:
        print(f"guardian error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("guardian error: interrupted", file=sys.stderr)
        return 2
    except Exception as exc:  # Defensive: surface unexpected failures clearly.
        print(f"guardian internal error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
