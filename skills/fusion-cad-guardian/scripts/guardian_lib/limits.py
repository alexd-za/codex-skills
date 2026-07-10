from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .errors import GuardianError


@dataclass(frozen=True)
class ResourceLimits:
    """Hard preflight limits for untrusted or unexpectedly large inputs."""

    max_file_size_mb: float = 512.0
    max_triangles: int = 5_000_000
    max_coordinate_abs_mm: float = 1_000_000.0
    max_estimated_memory_mb: float = 2048.0
    max_archive_entries: int = 2048
    max_archive_uncompressed_mb: float = 1024.0
    max_compression_ratio: float = 200.0

    def validate(self) -> "ResourceLimits":
        numeric_positive = {
            "max_file_size_mb": self.max_file_size_mb,
            "max_triangles": self.max_triangles,
            "max_coordinate_abs_mm": self.max_coordinate_abs_mm,
            "max_estimated_memory_mb": self.max_estimated_memory_mb,
            "max_archive_entries": self.max_archive_entries,
            "max_archive_uncompressed_mb": self.max_archive_uncompressed_mb,
            "max_compression_ratio": self.max_compression_ratio,
        }
        for name, value in numeric_positive.items():
            if value <= 0:
                raise GuardianError(f"{name} must be positive")
        return self

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_RESOURCE_LIMITS = ResourceLimits()
_LIMIT_FIELDS = set(DEFAULT_RESOURCE_LIMITS.to_dict())
_INT_FIELDS = {"max_triangles", "max_archive_entries"}


def limits_from_mapping(data: Any | None, *, base: ResourceLimits | None = None) -> ResourceLimits:
    """Build limits from JSON-like input, defaulting missing fields to ``base``."""

    current = base or DEFAULT_RESOURCE_LIMITS
    if data is None:
        return current.validate()
    if not isinstance(data, dict):
        raise GuardianError("resource_limits must be an object")
    unknown = set(data) - _LIMIT_FIELDS
    if unknown:
        raise GuardianError(f"resource_limits has unknown keys: {sorted(unknown)}")
    values = current.to_dict()
    values.update(data)
    try:
        converted = {
            key: int(value) if key in _INT_FIELDS else float(value)
            for key, value in values.items()
        }
        result = ResourceLimits(**converted)
    except (TypeError, ValueError) as exc:
        raise GuardianError("resource_limits values must be numeric") from exc
    return result.validate()


def tighten_limits(primary: ResourceLimits, requested: Any | None) -> ResourceLimits:
    """Allow a contract to tighten safety limits, never silently loosen them."""

    if requested is None:
        return primary.validate()
    candidate = limits_from_mapping(requested, base=primary)
    values = {
        key: min(primary.to_dict()[key], candidate.to_dict()[key])
        for key in _LIMIT_FIELDS
    }
    values["max_triangles"] = int(values["max_triangles"])
    values["max_archive_entries"] = int(values["max_archive_entries"])
    return ResourceLimits(**values).validate()


def estimated_mesh_memory_mb(triangle_count: int) -> float:
    """Conservative estimate for Python object-heavy triangle analysis."""

    return triangle_count * 640.0 / (1024.0 * 1024.0)
