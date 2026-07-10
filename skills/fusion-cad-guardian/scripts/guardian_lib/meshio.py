from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path, PurePosixPath
from typing import Any
import xml.etree.ElementTree as ET
import zipfile

from .core import Triangle, read_stl
from .errors import GuardianError
from .limits import ResourceLimits, estimated_mesh_memory_mb

_UNIT_TO_MM = {
    "micron": 0.001,
    "millimeter": 1.0,
    "centimeter": 10.0,
    "inch": 25.4,
    "foot": 304.8,
    "meter": 1000.0,
}
_MODEL_REL_SUFFIX = "/3dmodel"

Matrix = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]

IDENTITY: Matrix = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _safe_xml(data: bytes, label: str) -> ET.Element:
    upper = data[:8192].upper()
    if b"<!DOCTYPE" in upper or b"<!ENTITY" in upper:
        raise GuardianError(f"{label} contains a forbidden DTD/entity declaration")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise GuardianError(f"invalid XML in {label}: {exc}") from exc


def _parse_transform(value: str | None, label: str) -> Matrix:
    if not value:
        return IDENTITY
    parts = value.split()
    if len(parts) != 12:
        raise GuardianError(f"{label} transform must contain 12 numbers")
    try:
        numbers = [float(item) for item in parts]
    except ValueError as exc:
        raise GuardianError(f"{label} transform contains a non-numeric value") from exc
    if not all(math.isfinite(item) for item in numbers):
        raise GuardianError(f"{label} transform contains non-finite values")
    return (
        (numbers[0], numbers[1], numbers[2], 0.0),
        (numbers[3], numbers[4], numbers[5], 0.0),
        (numbers[6], numbers[7], numbers[8], 0.0),
        (numbers[9], numbers[10], numbers[11], 1.0),
    )


def _multiply(left: Matrix, right: Matrix) -> Matrix:
    # Row-vector convention: point * left * right.
    return tuple(
        tuple(sum(left[row][k] * right[k][column] for k in range(4)) for column in range(4))
        for row in range(4)
    )  # type: ignore[return-value]


def _apply(vertex: tuple[float, float, float], matrix: Matrix, scale: float) -> tuple[float, float, float]:
    x, y, z = vertex
    result = (
        x * matrix[0][0] + y * matrix[1][0] + z * matrix[2][0] + matrix[3][0],
        x * matrix[0][1] + y * matrix[1][1] + z * matrix[2][1] + matrix[3][1],
        x * matrix[0][2] + y * matrix[1][2] + z * matrix[2][2] + matrix[3][2],
    )
    return result[0] * scale, result[1] * scale, result[2] * scale


def _check_vertex(vertex: tuple[float, float, float], limits: ResourceLimits, label: str) -> None:
    if not all(math.isfinite(value) for value in vertex):
        raise GuardianError(f"{label} contains invalid coordinates")
    if any(abs(value) > limits.max_coordinate_abs_mm for value in vertex):
        raise GuardianError(
            f"{label} exceeds max_coordinate_abs_mm={limits.max_coordinate_abs_mm:g}"
        )


def _safe_member_name(name: str) -> bool:
    path = PurePosixPath(name.replace("\\", "/"))
    return not path.is_absolute() and ".." not in path.parts and bool(path.parts)


def preflight_3mf(path: Path, limits: ResourceLimits) -> dict[str, Any]:
    limits.validate()
    if not path.is_file():
        raise GuardianError(f"3MF file not found: {path}")
    size = path.stat().st_size
    if size > int(limits.max_file_size_mb * 1024 * 1024):
        raise GuardianError(
            f"3MF size {size} bytes exceeds max_file_size_mb={limits.max_file_size_mb:g}"
        )
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            if len(infos) > limits.max_archive_entries:
                raise GuardianError(
                    f"3MF contains {len(infos)} entries, exceeding max_archive_entries={limits.max_archive_entries}"
                )
            total_uncompressed = 0
            total_compressed = 0
            for info in infos:
                if not _safe_member_name(info.filename):
                    raise GuardianError(f"unsafe 3MF archive member path: {info.filename!r}")
                if info.flag_bits & 0x1:
                    raise GuardianError(f"encrypted 3MF archive member is not supported: {info.filename}")
                total_uncompressed += info.file_size
                total_compressed += info.compress_size
                if info.file_size and info.compress_size == 0:
                    raise GuardianError(f"3MF archive member has an invalid compression ratio: {info.filename}")
                ratio = info.file_size / max(info.compress_size, 1)
                if ratio > limits.max_compression_ratio:
                    raise GuardianError(
                        f"3MF member compression ratio {ratio:.1f} exceeds max_compression_ratio={limits.max_compression_ratio:g}"
                    )
            if total_uncompressed > int(limits.max_archive_uncompressed_mb * 1024 * 1024):
                raise GuardianError(
                    f"3MF uncompressed size exceeds max_archive_uncompressed_mb={limits.max_archive_uncompressed_mb:g}"
                )
            total_ratio = total_uncompressed / max(total_compressed, 1)
            if total_ratio > limits.max_compression_ratio:
                raise GuardianError(
                    f"3MF total compression ratio {total_ratio:.1f} exceeds max_compression_ratio={limits.max_compression_ratio:g}"
                )
    except zipfile.BadZipFile as exc:
        raise GuardianError(f"invalid 3MF ZIP container: {path}") from exc
    return {
        "size_bytes": size,
        "archive_entries": len(infos),
        "archive_uncompressed_bytes": total_uncompressed,
        "archive_compressed_bytes": total_compressed,
        "archive_compression_ratio": total_ratio,
        "limits": limits.to_dict(),
    }


@dataclass
class _Object:
    object_id: str
    name: str
    object_type: str
    vertices: list[tuple[float, float, float]]
    triangles: list[tuple[int, int, int]]
    components: list[tuple[str, Matrix]]


@dataclass
class _Model:
    unit: str
    scale_mm: float
    objects: dict[str, _Object]
    build: list[tuple[str, Matrix]]
    model_part: str


def _model_part_name(archive: zipfile.ZipFile) -> str:
    names = set(archive.namelist())
    if "_rels/.rels" in names:
        root = _safe_xml(archive.read("_rels/.rels"), "_rels/.rels")
        for element in root.iter():
            if _local(element.tag) != "Relationship":
                continue
            rel_type = element.attrib.get("Type", "")
            target = element.attrib.get("Target", "").lstrip("/")
            if rel_type.endswith(_MODEL_REL_SUFFIX) and target in names:
                return target
    candidates = sorted(name for name in names if name.lower().endswith(".model"))
    if not candidates:
        raise GuardianError("3MF archive contains no .model part")
    return candidates[0]


def _parse_model(path: Path, limits: ResourceLimits) -> tuple[_Model, dict[str, Any]]:
    preflight = preflight_3mf(path, limits)
    with zipfile.ZipFile(path) as archive:
        part = _model_part_name(archive)
        root = _safe_xml(archive.read(part), part)
    if _local(root.tag) != "model":
        raise GuardianError("3MF model part root element is not <model>")
    unit = root.attrib.get("unit", "millimeter").lower()
    if unit not in _UNIT_TO_MM:
        raise GuardianError(f"unsupported 3MF unit: {unit}")
    objects: dict[str, _Object] = {}
    build: list[tuple[str, Matrix]] = []
    for element in root.iter():
        tag = _local(element.tag)
        if tag == "object":
            object_id = element.attrib.get("id", "")
            if not object_id or object_id in objects:
                raise GuardianError(f"invalid or duplicate 3MF object id: {object_id!r}")
            name = element.attrib.get("name", "")
            object_type = element.attrib.get("type", "model")
            vertices: list[tuple[float, float, float]] = []
            triangles: list[tuple[int, int, int]] = []
            components: list[tuple[str, Matrix]] = []
            for child in element.iter():
                child_tag = _local(child.tag)
                if child_tag == "vertex":
                    try:
                        vertex = (
                            float(child.attrib["x"]),
                            float(child.attrib["y"]),
                            float(child.attrib["z"]),
                        )
                    except (KeyError, ValueError) as exc:
                        raise GuardianError(f"object {object_id} contains an invalid vertex") from exc
                    vertices.append(vertex)
                elif child_tag == "triangle":
                    try:
                        triangle = (
                            int(child.attrib["v1"]),
                            int(child.attrib["v2"]),
                            int(child.attrib["v3"]),
                        )
                    except (KeyError, ValueError) as exc:
                        raise GuardianError(f"object {object_id} contains an invalid triangle") from exc
                    triangles.append(triangle)
                elif child_tag == "component":
                    ref = child.attrib.get("objectid", "")
                    if not ref:
                        raise GuardianError(f"object {object_id} contains a component without objectid")
                    components.append((ref, _parse_transform(child.attrib.get("transform"), f"component {ref}")))
            if vertices and components:
                raise GuardianError(f"3MF object {object_id} cannot contain both a mesh and components")
            if triangles and not vertices:
                raise GuardianError(f"3MF object {object_id} has triangles but no vertices")
            for triangle in triangles:
                if any(index < 0 or index >= len(vertices) for index in triangle):
                    raise GuardianError(f"3MF object {object_id} triangle references an invalid vertex")
            objects[object_id] = _Object(object_id, name, object_type, vertices, triangles, components)
    # ElementTree has no parent lookup; inspect direct build children separately.
    for element in root.iter():
        if _local(element.tag) != "build":
            continue
        for item in list(element):
            if _local(item.tag) != "item":
                continue
            object_id = item.attrib.get("objectid", "")
            if not object_id:
                raise GuardianError("3MF build item is missing objectid")
            build.append((object_id, _parse_transform(item.attrib.get("transform"), f"build item {object_id}")))
    for object_id, obj in objects.items():
        for ref, _transform in obj.components:
            if ref not in objects:
                raise GuardianError(f"3MF object {object_id} references missing component object {ref}")
    for object_id, _transform in build:
        if object_id not in objects:
            raise GuardianError(f"3MF build references missing object {object_id}")
    preflight.update({"model_part": part, "unit": unit, "unit_scale_mm": _UNIT_TO_MM[unit]})
    return _Model(unit, _UNIT_TO_MM[unit], objects, build, part), preflight


def _flatten_object(
    model: _Model,
    object_id: str,
    transform: Matrix,
    limits: ResourceLimits,
    stack: tuple[str, ...],
) -> list[Triangle]:
    if object_id in stack:
        raise GuardianError(f"3MF component cycle detected: {' -> '.join((*stack, object_id))}")
    obj = model.objects[object_id]
    if obj.vertices:
        estimated = estimated_mesh_memory_mb(len(obj.triangles))
        if len(obj.triangles) > limits.max_triangles or estimated > limits.max_estimated_memory_mb:
            raise GuardianError("3MF object exceeds triangle or estimated-memory limits")
        converted = [_apply(vertex, transform, model.scale_mm) for vertex in obj.vertices]
        for index, vertex in enumerate(converted):
            _check_vertex(vertex, limits, f"3MF object {object_id} vertex {index}")
        return [
            (converted[a], converted[b], converted[c])
            for a, b, c in obj.triangles
        ]
    triangles: list[Triangle] = []
    for ref, child_transform in obj.components:
        triangles.extend(
            _flatten_object(
                model,
                ref,
                _multiply(child_transform, transform),
                limits,
                (*stack, object_id),
            )
        )
        if len(triangles) > limits.max_triangles:
            raise GuardianError(f"flattened 3MF exceeds max_triangles={limits.max_triangles}")
        if estimated_mesh_memory_mb(len(triangles)) > limits.max_estimated_memory_mb:
            raise GuardianError("flattened 3MF exceeds estimated-memory limit")
    return triangles


def inspect_3mf(path: Path, *, limits: ResourceLimits | None = None) -> dict[str, Any]:
    active = (limits or ResourceLimits()).validate()
    model, preflight = _parse_model(path, active)
    objects = []
    for obj in model.objects.values():
        objects.append({
            "object_id": obj.object_id,
            "name": obj.name,
            "type": obj.object_type,
            "mesh_vertex_count": len(obj.vertices),
            "mesh_triangle_count": len(obj.triangles),
            "component_count": len(obj.components),
            "in_build": any(item_id == obj.object_id for item_id, _ in model.build),
        })
    return {
        "format": "3mf",
        "path": str(path.resolve()),
        "unit": model.unit,
        "unit_scale_mm": model.scale_mm,
        "model_part": model.model_part,
        "build_item_count": len(model.build),
        "objects": objects,
        "preflight": preflight,
    }


def _select_3mf_object(
    model: _Model,
    *,
    object_id: str | None,
    object_name: str | None,
) -> tuple[str, str, Matrix, int | None]:
    selected_id: str | None = None
    if object_id:
        if object_id not in model.objects:
            raise GuardianError(f"3MF object id not found: {object_id}")
        selected_id = object_id
    elif object_name:
        exact = [obj.object_id for obj in model.objects.values() if obj.name == object_name]
        folded = [obj.object_id for obj in model.objects.values() if obj.name.casefold() == object_name.casefold()]
        matches = exact or folded
        if len(matches) != 1:
            raise GuardianError(f"3MF object name must identify exactly one object: {object_name!r}")
        selected_id = matches[0]
    elif len(model.build) == 1:
        selected_id = model.build[0][0]
    elif not model.build:
        candidates = [obj.object_id for obj in model.objects.values() if obj.vertices or obj.components]
        if len(candidates) == 1:
            selected_id = candidates[0]
    if selected_id is None:
        raise GuardianError("3MF contains multiple selectable objects; use --object-id or --object-name")
    build_matches = [(index, transform) for index, (item_id, transform) in enumerate(model.build) if item_id == selected_id]
    if len(build_matches) > 1:
        raise GuardianError(f"3MF object {selected_id} appears in multiple build items; select a unique exported object")
    build_index, transform = build_matches[0] if build_matches else (None, IDENTITY)
    return selected_id, model.objects[selected_id].name, transform, build_index


def read_3mf(
    path: Path,
    *,
    limits: ResourceLimits | None = None,
    object_id: str | None = None,
    object_name: str | None = None,
) -> tuple[list[Triangle], dict[str, Any], dict[str, Any]]:
    active = (limits or ResourceLimits()).validate()
    model, preflight = _parse_model(path, active)
    selected_id, selected_name, transform, build_index = _select_3mf_object(
        model, object_id=object_id, object_name=object_name
    )
    triangles = _flatten_object(model, selected_id, transform, active, ())
    if not triangles:
        raise GuardianError(f"3MF object {selected_id} contains no triangles")
    if len(triangles) > active.max_triangles:
        raise GuardianError(f"3MF contains {len(triangles)} triangles, exceeding max_triangles={active.max_triangles}")
    estimated = estimated_mesh_memory_mb(len(triangles))
    if estimated > active.max_estimated_memory_mb:
        raise GuardianError("3MF estimated analysis memory exceeds configured limit")
    preflight.update({"triangle_count": len(triangles), "estimated_memory_mb": estimated})
    metadata = {
        "container": "3mf",
        "unit": model.unit,
        "unit_scale_mm": model.scale_mm,
        "model_part": model.model_part,
        "object_id": selected_id,
        "object_name": selected_name,
        "build_index": build_index,
    }
    return triangles, preflight, metadata


def read_mesh(
    path: Path,
    *,
    limits: ResourceLimits | None = None,
    object_id: str | None = None,
    object_name: str | None = None,
) -> tuple[str, list[Triangle], dict[str, Any], dict[str, Any]]:
    suffix = path.suffix.lower()
    active = (limits or ResourceLimits()).validate()
    if suffix == ".stl":
        if object_id or object_name:
            raise GuardianError("--object-id/--object-name apply only to 3MF inputs")
        stl_format, triangles, preflight = read_stl(path, limits=active)
        return f"stl-{stl_format}", triangles, preflight, {"container": "stl"}
    if suffix == ".3mf":
        triangles, preflight, metadata = read_3mf(
            path, limits=active, object_id=object_id, object_name=object_name
        )
        return "3mf", triangles, preflight, metadata
    raise GuardianError("unsupported mesh format; expected .stl or .3mf")
