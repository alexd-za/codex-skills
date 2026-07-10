# Acceptance gate

The gate combines three independent evidence classes:

1. live-model and engineering evidence from `evidence.json`;
2. contract-backed STL reports;
3. export provenance linking each audited STL to the recorded Fusion document and checkpoint.

## Mesh report requirements

A mesh report satisfies the gate only when:

- its verdict is `PASS`;
- it was generated with a contract, not audit-only mode;
- its embedded contract SHA-256 matches the current contract;
- its STL SHA-256 matches a complete export record.

Changing the contract after auditing invalidates the old report. Re-run the audit.

## Verdict precedence

1. Any required or mesh failure -> `FAIL`.
2. Missing required evidence, stale contract report, missing mesh report, or incomplete provenance -> `INCOMPLETE`.
3. Required checks pass but optional engineering checks remain -> `CONDITIONAL_PASS`.
4. Everything passes -> `PASS`.

A conditional pass is not permission to skip safety-critical engineering review.
