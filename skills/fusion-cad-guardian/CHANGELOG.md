# Changelog

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
