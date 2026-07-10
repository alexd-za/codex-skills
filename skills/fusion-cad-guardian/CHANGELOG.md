# Changelog

## 2.2.0 — 2026-07-10

Final stabilization and manufacturing-evidence release for the current feature cycle.

### Added

- Resource-limited core 3MF auditing with standard unit conversion, mesh objects, components, build items, and transforms.
- Explicit 3MF object selection by ID or name and an `inspect-3mf` discovery command.
- 3MF ZIP/XML defenses for traversal, encryption, archive expansion, compression ratios, DTD/entity declarations, invalid transforms, component cycles, and pathological coordinates.
- Existing-G-code metadata parsing for common generator, print-time, filament, layer, nozzle, and maximum-Z comments.
- Source-mesh-linked slicer reports and optional contract criteria integrated into the final gate.
- Standalone escaped HTML reports for mesh audits, slicer evidence, comparisons, and acceptance results.
- Integrity-checked verification bundles with streamed creation, streamed verification, manifests, SHA-256 checks, and archive resource limits.
- `bundle`, `bundle-verify`, `inspect-3mf`, `slicer-audit`, `migrate`, and `doctor` commands.
- `export_3mf` capability-profile key while retaining `export_stl` compatibility.
- Slicer-report and bundle-manifest JSON Schemas, bringing the total to seven.
- Project `gcode/` and `bundles/` directories.
- 41 dependency-free unit tests plus schema-conformance validation.

### Changed

- Contract schema revision is now `2.2` while retaining `schema_version: 2` compatibility.
- Mesh auditing accepts `.stl` and `.3mf`; `audit_stl` remains as a compatibility alias.
- Slicer evidence can be required per project or per part and must link to the current contract and source mesh when configured.
- Bundle and 3MF inputs share explicit archive limits for entries, expanded size, and compression ratio.
- `doctor` verifies version consistency, manifest completeness, self-test status, and optional project artifacts.
- Reports expose source-format and selected-3MF-object metadata.
- Documentation distinguishes core 3MF and metadata parsing from unsupported advanced 3MF/slicer behavior.

### Security and integrity

- Guardian still never executes arbitrary Python inside Fusion or launches external CAD/slicer applications.
- Untrusted archive inputs are preflighted before model or manifest processing.
- Required checks cannot be bypassed with `NOT_APPLICABLE`.
- Audit-only, stale-contract, wrong-part, wrong-source-mesh, or incomplete-provenance reports cannot satisfy the final gate.


## 2.1.0 — 2026-07-10

Focused interoperability, safety, and multi-part release.

### Added

- JSON Schema Draft 2020-12 documents for contracts, evidence ledgers, export records, capability profiles, and audit reports.
- `$schema` links in generated contract, evidence, capability, and audit artifacts.
- Fusion MCP capability profiles with `available`, `unavailable`, and `unknown` states.
- `capabilities-init`, `capabilities-set`, and `plan` commands.
- Requirement-to-capability routing that reports `READY`, `DISCOVERY_REQUIRED`, or `BLOCKED` without invoking live CAD operations.
- Multi-part contracts with stable `part_id`, part-specific mesh criteria, namespaced evidence, and part-linked export provenance.
- `--part` project/init scaffolding, `part-add`, and `--part-id` auditing.
- Final-gate completeness checks for every required part.
- STL preflight limits for file size, triangle count, coordinate magnitude, and estimated Python memory.
- Contract-level resource limits that may tighten but never silently loosen runtime limits.
- Validation for capability profiles and audit reports.
- 21-unit-test suite covering new capability, resource, schema, and multi-part behavior.

### Changed

- Contract schema revision is now `2.1` while retaining `schema_version: 2` compatibility.
- Fusion requirements may declare a capability mapping.
- Project scaffolds now include `capabilities.json`.
- Batch jobs may include `part_id`.
- Regression comparison refuses reports for different part identities.
- Audit reports now include effective resource limits and input-preflight evidence.

## 2.0.0 — 2026-07-10

Major verification-layer release.

### Added

- Schema-v2 design contracts separating Fusion, mesh, and engineering requirements.
- `project` command for a complete verification workspace.
- Evidence ledger with source, method, evidence, status, and required/optional semantics.
- `evidence-init`, `evidence-hash`, `validate`, and `gate` commands.
- Export provenance requiring a matching STL SHA-256 plus Fusion document, checkpoint, export method, and body/component identity.
- Contract SHA-256 linkage in mesh reports.
- Final acceptance gate with `PASS`, `CONDITIONAL_PASS`, `INCOMPLETE`, and `FAIL`.
- Uniform-density centre-of-mass calculation for watertight meshes.
- Optional mass checks from volume and density.
- Triangle quality, sliver detection, edge-length statistics, build-plate contact area, and downward-facing-area heuristics.
- Explicit capability-routing and claim-discipline references.
- Compatibility with v1 mesh-contract files.

### Changed

- Guardian is defined strictly as a companion to Fusion MCP, never a live-CAD controller.
- Audit-only reports can no longer satisfy the final gate.
- Required `NOT_APPLICABLE` checks are incomplete rather than silently passing.
- PASS and FAIL evidence require concrete method and evidence.
- Repair workflow now updates evidence and export provenance after each revision.

## 1.0.0 — 2026-07-10

Initial release.

- Machine-readable mesh contract.
- Dependency-free ASCII/binary STL auditing.
- Dimensions, topology, shell, winding, area, and volume checks.
- Batch auditing and before/after regression comparison.
- Fusion semantic verification guidance and bounded repair loop.
