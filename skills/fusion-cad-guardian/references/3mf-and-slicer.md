# 3MF and slicer evidence

## Core 3MF support

Guardian treats 3MF as an untrusted ZIP/XML container and supports the core manufacturing-model subset needed for deterministic triangle analysis:

- model-part discovery through package relationships or `.model` fallback;
- `micron`, `millimeter`, `centimeter`, `inch`, `foot`, and `meter` units converted to millimetres;
- mesh objects with indexed vertices/triangles;
- component objects;
- object/component/build transforms;
- build-item discovery;
- explicit object selection by object ID or exact object name.

When the build contains more than one selectable object, `audit` must receive `--object-id` or `--object-name`. Never choose an object merely because it appears first.

Guardian does not interpret advanced 3MF materials, colours, textures, beam lattices, slices, production extensions, secure content, or vendor-specific metadata. Treat those as external evidence.

## Archive and XML safety

Before parsing, Guardian rejects:

- absolute or parent-traversal member names;
- encrypted members;
- excessive entry counts;
- excessive expanded size;
- excessive per-entry or total compression ratios;
- DTD or entity declarations;
- invalid/non-finite transforms;
- invalid triangle indices;
- missing component references;
- component cycles;
- coordinate or triangle counts above configured limits.

## G-code evidence

`slicer-audit` reads an existing G-code file. It does not execute OrcaSlicer, PrusaSlicer, Bambu Studio, Cura, or any other application.

The parser recognizes common comment forms for:

- generator name;
- estimated print time;
- filament length, volume, and mass;
- layer count;
- layer and first-layer height;
- nozzle diameter;
- maximum Z.

Comment formats vary between slicers and versions. A missing field is missing evidence, not a value of zero. Review the generated report before relying on it.

When `source_mesh` is supplied, the report records its SHA-256. The final gate can require that hash to match the current mesh audit.

G-code metadata is not proof that:

- the slicer interpreted every feature correctly;
- toolpaths are collision-free;
- supports, temperatures, speeds, adhesion, or material settings are suitable;
- the physical print will succeed.
