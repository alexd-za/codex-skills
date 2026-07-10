# Capability boundaries

## Fusion MCP can establish

Subject to the tools actually exposed by the connected server:

- active document and design context;
- named parameters and critical dimensions;
- component, body, sketch and feature structure;
- sketch constraint state;
- feature/timeline health;
- joint type, axis, limits and sampled positions;
- interference and clearance at inspected positions;
- selected export body/component;
- save/version/checkpoint identity.

Record these results in the evidence ledger.

## Guardian can establish from STL

- file identity and size;
- overall axis-aligned dimensions;
- topology indicators;
- edge-connected shells;
- triangle defects and quality;
- surface area;
- signed and absolute enclosed volume;
- uniform-density centre of mass when watertight;
- estimated mass when density is supplied;
- configured build-plane and orientation heuristics.

## Guardian cannot establish from STL

- parametric intent or named dimensions;
- component identity unless export provenance records it;
- continuous collision-free motion;
- joint definitions;
- minimum wall thickness;
- local hole positions, fits or clearances;
- structural strength, fatigue, impact resistance or safety factor;
- slicer support generation or real print quality;
- material/process suitability;
- rules compliance.

Use the proper Fusion tool, calculation, simulation, slicer, physical test, or human review. Otherwise mark the claim `NOT_VERIFIED`.


## v2.2 exported-file boundary

Guardian may inspect STL, the supported core subset of 3MF, and metadata in an existing G-code file. This remains exported-file evidence. It does not authorize live Fusion changes, slicer execution, or claims about physical manufacture.
