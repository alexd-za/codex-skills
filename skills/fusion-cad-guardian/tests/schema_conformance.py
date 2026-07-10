"""Optional CI conformance checks for the published JSON Schemas.

This file is not imported by the dependency-free runtime or unittest discovery.
CI installs jsonschema and invokes it explicitly.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from guardian_lib.core import cube_triangles, write_binary_stl
from guardian_lib.reports import audit_stl


def main() -> int:
    schemas = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in (ROOT / "schemas").glob("*.json")
    }
    registry = Registry().with_resources(
        [(schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()]
    )
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)

    cases = [
        ("contract.schema.json", ROOT / "assets" / "contract.example.json"),
        ("evidence.schema.json", ROOT / "assets" / "evidence.example.json"),
        ("capability-profile.schema.json", ROOT / "assets" / "capabilities.example.json"),
    ]
    for schema_name, instance_path in cases:
        instance = json.loads(instance_path.read_text(encoding="utf-8"))
        Draft202012Validator(schemas[schema_name], registry=registry).validate(instance)

    with tempfile.TemporaryDirectory(prefix="guardian-schema-") as directory:
        mesh = Path(directory) / "cube.stl"
        write_binary_stl(mesh, cube_triangles())
        report = audit_stl(mesh)
        Draft202012Validator(schemas["audit-report.schema.json"], registry=registry).validate(report)

    print(f"Validated {len(schemas)} schemas and {len(cases) + 1} example artifacts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
