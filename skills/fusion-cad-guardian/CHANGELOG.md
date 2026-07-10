# Changelog

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
- 22-unit-test suite covering capability, resource, schema, provenance, gate, and multi-part behavior.

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
