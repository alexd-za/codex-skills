# Acceptance gate

The gate combines:

1. live-model and engineering evidence from `evidence.json`;
2. contract-backed STL reports;
3. export provenance linking each audited STL to the recorded Fusion document, checkpoint, body/component, and part identity;
4. multi-part completeness when the contract defines required parts.

## Mesh report requirements

A mesh report satisfies the gate only when:

- its verdict is `PASS`;
- it was generated with a contract, not audit-only mode;
- its embedded contract SHA-256 matches the current contract;
- its STL SHA-256 matches a complete export record;
- its `part_id` matches the export record when using a multi-part contract.

Changing the contract after auditing invalidates the old report. Re-run the audit.

## Multi-part completeness

Every `parts[]` entry with `required: true` needs a current passing report. Missing a required part produces `INCOMPLETE`, even when all submitted reports pass.

## Verdict precedence

1. Any required evidence or mesh failure -> `FAIL`.
2. Missing required evidence, stale contract report, missing required part, or incomplete provenance -> `INCOMPLETE`.
3. Required checks pass but optional engineering checks remain -> `CONDITIONAL_PASS`.
4. Everything passes -> `PASS`.

A conditional pass is not permission to skip safety-critical engineering review.


## Slicer evidence

When a project or part sets `slicer.required: true`, the gate requires a current passing slicer report. If source-mesh linkage is required, its SHA-256 must match the current mesh report for that part.
