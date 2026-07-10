# Design contract schema v2

A schema-v2 contract has four concerns:

- identity: `part_name`, `task_type`, and `units`;
- `mesh`: deterministic STL criteria;
- `fusion_requirements`: live-model evidence requirements;
- `engineering_requirements`: calculation, simulation, slicer, physical-test, or human-review requirements.

`export_provenance_required` should remain `true` for final acceptance.

## Range syntax

Use either:

```json
{"target": 20.0, "tolerance": 0.1}
```

or:

```json
{"min": 19.9, "max": 20.1}
```

## Mesh criteria

Supported criteria include:

- `expected_dimensions_mm`
- `volume_mm3`
- `surface_area_mm2`
- `mass_g` with `density_g_cm3`
- manifold and triangle-defect limits
- `max_sliver_triangles`
- `min_triangle_quality`
- triangle count range
- positive signed volume
- `build_plate`
- `orientation`

Do not encode a local feature tolerance as an overall bounding-box dimension.

## Requirement semantics

Each requirement contains:

```json
{
  "id": "critical_parameters",
  "required": true,
  "description": "Mount spacing and fastener diameters verified in Fusion"
}
```

Use stable, unique IDs because the evidence ledger maps by ID.

Schema-v1 mesh contracts remain accepted for backwards compatibility, but they cannot express Fusion or engineering evidence and are not recommended for new work.
