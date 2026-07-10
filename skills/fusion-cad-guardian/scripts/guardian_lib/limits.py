from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .errors import GuardianError


@dataclass(frozen=True)
class ResourceLimits:
    """Hard preflight limits for untrusted or unexpectedly large mesh inputs."""

    max_file_size_mb: float = 512.0
    max_triangles: int = 5_000_000
    max_coordinate_abs_mm: float = 1_000_000.0
    max_estimated_memory_mb: float = 2048.0

    def validate(self) -> "ResourceLimits":
        if self.max_file_size_mb <= 0:
            raise GuardianError("max_file_size_mb must be positive")
        if self.max_triangles <= 0:
            raise GuardianError("max_triangles must be positive")
        if self.max_coordinate_abs_mm <= 0:
            raise GuardianError("max_coordinate_abs_mm must be positive")
        if self.max_estimated_memory_mb <= 0:
            raise GuardianError("max_estimated_memory_mb must be positive")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_RESOURCE_LIMITS = ResourceLimits()


def limits_from_mapping(data: Any | None, *, base: ResourceLimits | None = None) -> ResourceLimits:
    """Build limits from JSON-like input, defaulting missing fields to ``base``."""

    current = base or DEFAULT_RESOURCE_LIMITS
    if data is None:
        return current.validate()
    if not isinstance(data, dict):
        raise GuardianError("resource_limits must be an object")
    allowed = {
        "max_file_size_mb",
        "max_triangles",
        "max_coordinate_abs_mm",
        "max_estimated_memory_mb",
    }
    unknown = set(data) - allowed
    if unknown:
        raise GuardianError(f"resource_limits has unknown keys: {sorted(unknown)}")
    values = current.to_dict()
    values.update(data)
    try:
        result = ResourceLimits(
            max_file_size_mb=float(values["max_file_size_mb"]),
            max_triangles=int(values["max_triangles"]),
            max_coordinate_abs_mm=float(values["max_coordinate_abs_mm"]),
            max_estimated_memory_mb=float(values["max_estimated_memory_mb"]),
        )
    except (TypeError, ValueError) as exc:
        raise GuardianError("resource_limits values must be numeric") from exc
    return result.validate()


def tighten_limits(primary: ResourceLimits, requested: Any | None) -> ResourceLimits:
    """Allow a contract to tighten safety limits, never silently loosen them."""

    if requested is None:
        return primary.validate()
    candidate = limits_from_mapping(requested, base=primary)
    return ResourceLimits(
        max_file_size_mb=min(primary.max_file_size_mb, candidate.max_file_size_mb),
        max_triangles=min(primary.max_triangles, candidate.max_triangles),
        max_coordinate_abs_mm=min(primary.max_coordinate_abs_mm, candidate.max_coordinate_abs_mm),
        max_estimated_memory_mb=min(primary.max_estimated_memory_mb, candidate.max_estimated_memory_mb),
    ).validate()


def estimated_mesh_memory_mb(triangle_count: int) -> float:
    """Conservative estimate for Python object-heavy triangle analysis."""

    # Python tuples/floats/dicts used by the analyser are substantially larger than
    # the 50-byte STL record. 640 bytes/triangle is intentionally conservative.
    return triangle_count * 640.0 / (1024.0 * 1024.0)
