from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
from typing import Any, Iterable
import zipfile

from . import VERSION
from .core import sha256_file
from .errors import GuardianError
from .limits import DEFAULT_RESOURCE_LIMITS, ResourceLimits

BUNDLE_MANIFEST_SCHEMA_URI = (
    "https://raw.githubusercontent.com/alexd-za/codex-skills/main/skills/"
    "fusion-cad-guardian/schemas/bundle-manifest.schema.json"
)


def utc_now() -> str:
    source_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if source_epoch:
        try:
            value = dt.datetime.fromtimestamp(int(source_epoch), tz=dt.timezone.utc)
        except (ValueError, OSError, OverflowError) as exc:
            raise GuardianError("SOURCE_DATE_EPOCH must be a valid Unix timestamp") from exc
        return value.replace(microsecond=0).isoformat()
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _safe_arcname(name: str) -> str:
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise GuardianError(f"unsafe bundle path: {name!r}")
    return str(path)


def _zip_info(name: str) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(_safe_arcname(name), date_time=(1980, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    return info


def _archive_preflight(path: Path, infos: list[zipfile.ZipInfo], limits: ResourceLimits) -> dict[str, Any]:
    size = path.stat().st_size
    if size > int(limits.max_file_size_mb * 1024 * 1024):
        raise GuardianError(f"bundle size exceeds max_file_size_mb={limits.max_file_size_mb:g}")
    if len(infos) > limits.max_archive_entries:
        raise GuardianError(f"bundle entry count exceeds max_archive_entries={limits.max_archive_entries}")
    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > int(limits.max_archive_uncompressed_mb * 1024 * 1024):
        raise GuardianError(
            "bundle uncompressed size exceeds "
            f"max_archive_uncompressed_mb={limits.max_archive_uncompressed_mb:g}"
        )
    for info in infos:
        _safe_arcname(info.filename)
        if info.flag_bits & 0x1:
            raise GuardianError(f"encrypted bundle member is unsupported: {info.filename}")
        ratio = info.file_size / max(info.compress_size, 1)
        if ratio > limits.max_compression_ratio:
            raise GuardianError(
                f"bundle member {info.filename!r} compression ratio {ratio:.1f} exceeds "
                f"max_compression_ratio={limits.max_compression_ratio:g}"
            )
    return {
        "size_bytes": size,
        "entry_count": len(infos),
        "uncompressed_bytes": total_uncompressed,
        "limits": limits.to_dict(),
    }


def validate_bundle_manifest(manifest: Any) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise GuardianError("bundle manifest must be an object")
    required = {"guardian_version", "generated_at", "metadata", "files"}
    missing = required - set(manifest)
    if missing:
        raise GuardianError(f"bundle manifest is missing fields: {sorted(missing)}")
    if not isinstance(manifest.get("metadata"), dict) or not isinstance(manifest.get("files"), list):
        raise GuardianError("bundle manifest metadata must be an object and files must be an array")
    names: set[str] = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or set(entry) != {"path", "sha256", "size_bytes"}:
            raise GuardianError("bundle manifest contains an invalid file entry")
        name = _safe_arcname(entry["path"])
        if name in names:
            raise GuardianError(f"bundle manifest contains duplicate path: {name}")
        names.add(name)
        if not isinstance(entry["sha256"], str) or not __import__("re").fullmatch(r"[0-9a-f]{64}", entry["sha256"]):
            raise GuardianError(f"bundle manifest contains invalid SHA-256 for {name}")
        if not isinstance(entry["size_bytes"], int) or entry["size_bytes"] < 0:
            raise GuardianError(f"bundle manifest contains invalid size for {name}")
    return manifest


def create_bundle(
    output: Path,
    files: Iterable[tuple[str, Path]],
    *,
    metadata: dict[str, Any] | None = None,
    limits: ResourceLimits | None = None,
) -> dict[str, Any]:
    active = (limits or DEFAULT_RESOURCE_LIMITS).validate()
    entries: list[dict[str, Any]] = []
    seen: set[str] = set()
    normalized: list[tuple[str, Path]] = []
    total_size = 0
    for arcname, source in files:
        safe_name = _safe_arcname(arcname)
        if safe_name == "manifest.json":
            raise GuardianError("manifest.json is reserved")
        if safe_name in seen:
            raise GuardianError(f"duplicate bundle path: {safe_name}")
        if not source.is_file():
            raise GuardianError(f"bundle input file not found: {source}")
        seen.add(safe_name)
        size = source.stat().st_size
        total_size += size
        normalized.append((safe_name, source))
        entries.append({"path": safe_name, "sha256": sha256_file(source), "size_bytes": size})
    if len(entries) + 1 > active.max_archive_entries:
        raise GuardianError(f"bundle input count exceeds max_archive_entries={active.max_archive_entries}")
    if total_size > int(active.max_archive_uncompressed_mb * 1024 * 1024):
        raise GuardianError(
            "bundle input size exceeds "
            f"max_archive_uncompressed_mb={active.max_archive_uncompressed_mb:g}"
        )
    entries.sort(key=lambda item: item["path"])
    manifest = validate_bundle_manifest({
        "$schema": BUNDLE_MANIFEST_SCHEMA_URI,
        "guardian_version": VERSION,
        "generated_at": utc_now(),
        "metadata": metadata or {},
        "files": entries,
    })
    manifest_bytes = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(_zip_info("manifest.json"), manifest_bytes)
        for arcname, source in sorted(normalized):
            with source.open("rb") as source_handle, archive.open(_zip_info(arcname), "w") as target:
                shutil.copyfileobj(source_handle, target, length=1024 * 1024)
    if output.stat().st_size > int(active.max_file_size_mb * 1024 * 1024):
        output.unlink(missing_ok=True)
        raise GuardianError(f"created bundle exceeds max_file_size_mb={active.max_file_size_mb:g}")
    return {
        "path": str(output.resolve()),
        "sha256": sha256_file(output),
        "size_bytes": output.stat().st_size,
        "manifest": manifest,
    }


def verify_bundle(path: Path, *, limits: ResourceLimits | None = None) -> dict[str, Any]:
    active = (limits or DEFAULT_RESOURCE_LIMITS).validate()
    if not path.is_file():
        raise GuardianError(f"bundle not found: {path}")
    try:
        with zipfile.ZipFile(path) as archive:
            infos = archive.infolist()
            preflight = _archive_preflight(path, infos, active)
            names: set[str] = set()
            for info in infos:
                safe = _safe_arcname(info.filename)
                if safe in names:
                    raise GuardianError(f"duplicate bundle member: {safe}")
                names.add(safe)
            if "manifest.json" not in names:
                raise GuardianError("bundle has no manifest.json")
            manifest_info = archive.getinfo("manifest.json")
            if manifest_info.file_size > 16 * 1024 * 1024:
                raise GuardianError("bundle manifest is unreasonably large")
            try:
                manifest = validate_bundle_manifest(json.loads(archive.read("manifest.json").decode("utf-8")))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise GuardianError("bundle manifest is invalid JSON") from exc
            expected_names = {"manifest.json"}
            checks: list[dict[str, Any]] = []
            for entry in manifest["files"]:
                name = _safe_arcname(entry["path"])
                expected_names.add(name)
                if name not in names:
                    checks.append({"path": name, "status": "MISSING"})
                    continue
                digest = hashlib.sha256()
                actual_size = 0
                with archive.open(name) as source:
                    while chunk := source.read(1024 * 1024):
                        actual_size += len(chunk)
                        digest.update(chunk)
                actual_hash = digest.hexdigest()
                ok = actual_hash == entry["sha256"] and actual_size == entry["size_bytes"]
                checks.append({
                    "path": name,
                    "status": "PASS" if ok else "FAIL",
                    "expected_sha256": entry["sha256"],
                    "actual_sha256": actual_hash,
                    "expected_size_bytes": entry["size_bytes"],
                    "actual_size_bytes": actual_size,
                })
            unexpected = sorted(names - expected_names)
            checks.extend({"path": name, "status": "UNEXPECTED"} for name in unexpected)
            passed = all(item["status"] == "PASS" for item in checks)
    except zipfile.BadZipFile as exc:
        raise GuardianError(f"invalid verification bundle: {path}") from exc
    return {
        "guardian_version": VERSION,
        "bundle": str(path.resolve()),
        "bundle_sha256": sha256_file(path),
        "passed": passed,
        "preflight": preflight,
        "checks": checks,
        "manifest": manifest,
    }


def project_bundle_files(project_dir: Path, *, include_exports: bool = False) -> list[tuple[str, Path]]:
    if not project_dir.is_dir():
        raise GuardianError(f"project directory not found: {project_dir}")
    preferred = ["contract.json", "evidence.json", "capabilities.json", "plan.json", "TASK.md"]
    files: list[tuple[str, Path]] = []
    for name in preferred:
        path = project_dir / name
        if path.is_file():
            files.append((name, path))
    for folder in ("reports", "snapshots"):
        directory = project_dir / folder
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.is_file():
                    files.append((str(path.relative_to(project_dir)).replace("\\", "/"), path))
    if include_exports:
        for folder in ("exports", "gcode"):
            directory = project_dir / folder
            if directory.is_dir():
                for path in sorted(directory.rglob("*")):
                    if path.is_file():
                        files.append((str(path.relative_to(project_dir)).replace("\\", "/"), path))
    if not files:
        raise GuardianError("project contains no bundleable files")
    return files
