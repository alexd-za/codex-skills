# Design contract schema v2.1

A current contract separates:

- project identity: `part_name`, `task_type`, `units`;
- one top-level `mesh` contract for a single output, or `parts[].mesh` for multiple outputs;
- `fusion_requirements`: live-model evidence requirements;
- `assembly_requirements`: cross-component or mechanism evidence;
- `engineering_requirements`: calculation, simulation, slicer, physical-test, or human-review requirements;
- `resource_limits`: input-safety limits that may only tighten runtime limits;
- `export_provenance_required`: whether each report must match a recorded Fusion export.

`schema_version` remains `2` for v2 compatibility. `schema_revision` is `2.1`.

## Range syntax

Use either:

```json
{"target": 20.0, "tolerance": 0.1}
```

or:

```json
{"min": 19.9, "max": 20.1}
```

## Requirement semantics

```json
{
  "id": "critical_parameters",
  "required": true,
  "capability": "read_parameters",
  "description": "Mount spacing and fastener diameters verified in Fusion"
}
```

`capability` maps the requirement to the MCP capability profile. It is optional for engineering requirements that do not belong to Fusion MCP.

## Multi-part semantics

Each part contains:

```json
{
  "id": "camera_bracket",
  "name": "Camera Bracket",
  "required": true,
  "mesh": {},
  "fusion_requirements": [],
  "engineering_requirements": []
}
```

Part IDs are stable machine identifiers and become evidence namespaces and export identities. See `multi-part.md`.

## Mesh criteria

Supported criteria include overall dimensions, volume, surface area, estimated mass, topology limits, triangle quality, build-plate contact, and orientation heuristics. Do not encode local feature tolerances as overall bounding-box dimensions.

Schema-v1 mesh contracts remain accepted for backward compatibility, but they cannot express capability routing, multi-part identity, or live-model evidence.
