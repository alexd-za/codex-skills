---
name: fusion-cad-guardian
description: Work alongside Autodesk Fusion MCP as a verification and acceptance layer. Use to profile the connected MCP's real capabilities, turn CAD requests into testable single-part or multi-part contracts, track Fusion and engineering evidence, prove export provenance, safely audit STL meshes under resource limits, compare revisions, and issue PASS, CONDITIONAL_PASS, INCOMPLETE, or FAIL. Never use this skill to replace Fusion MCP or perform live CAD editing.
---

# Fusion CAD Guardian 2.1

Fusion CAD Guardian is the **planning, evidence, exported-mesh, and acceptance layer** around a connected Fusion MCP server.

- **Fusion MCP owns the live design:** inspect, create, edit, measure, save checkpoints, test joints, check interference, and export.
- **Guardian owns verification discipline:** contracts, capability routing, evidence ledgers, export identity, deterministic STL analysis, regression comparison, and the final gate.

Guardian runs dependency-free Python outside Fusion. It does not install an add-in, invoke Fusion APIs, or execute arbitrary Python inside Fusion.

## Absolute boundary

| Operation | Owner |
|---|---|
| Create or modify Fusion geometry | Fusion MCP |
| Inspect live components, features, parameters, joints, or interference | Fusion MCP |
| Save/version/checkpoint the design | Fusion MCP |
| Export the intended body or component | Fusion MCP, or an explicitly recorded manual Fusion export |
| Discover and record which MCP capabilities exist | Guardian profile, based on actual MCP inspection |
| Define measurable acceptance criteria | Guardian contract |
| Track evidence and unresolved claims | Guardian evidence ledger |
| Audit exported STL topology and global geometry | Guardian auditor |
| Decide the final evidence-based verdict | Guardian gate |

Never route live CAD operations through Guardian. Never claim Guardian can compensate for a missing Fusion MCP operation.

Read `references/capability-boundaries.md` before making claims near this boundary.

## Required operating sequence

### 1. Inspect and profile the connected Fusion MCP

Discover the actual MCP tools. Do not assume names from documentation or another server.

Create a capability profile:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" capabilities-init `
  --out "fusion-guardian\capabilities.json" `
  --server-name "Autodesk Fusion MCP"
```

For each observed capability, record the concrete tool or method:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" capabilities-set `
  "fusion-guardian\capabilities.json" export_stl available `
  --tool "<actual-tool-name>"
```

Use only:

- `available` when a concrete tool or method was observed;
- `unavailable` after inspecting the server and confirming it is absent;
- `unknown` when discovery is incomplete.

An `available` capability requires a concrete tool or method. A server name is not evidence.

Read `references/capability-profile.md`.

### 2. Create a contract before editing

For a single output:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" init `
  --out "fusion-guardian\contract.json" `
  --part-name "Camera Bracket" `
  --task-type part
```

For a multi-part design or assembly:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" project "fusion-guardian" `
  --name "Rover Camera Mount" `
  --task-type assembly `
  --part "camera_bracket=Camera Bracket" `
  --part "sensor_cover=Sensor Cover"
```

The contract must separate:

- Fusion live-model requirements;
- assembly/mechanism requirements;
- per-part exported-mesh requirements;
- external engineering, calculation, slicer, simulation, or physical-test requirements;
- explicit resource limits for mesh inputs.

Do not silently invent critical dimensions, loads, materials, fits, or safety factors. State assumptions.

Read `references/design-contract.md` and `references/multi-part.md`.

### 3. Generate a capability-aware verification plan

```powershell
py -3 "<skill-dir>\scripts\guardian.py" plan `
  --contract "fusion-guardian\contract.json" `
  --capabilities "fusion-guardian\capabilities.json" `
  --json "fusion-guardian\plan.json"
```

Interpret readiness:

- `READY`: required mapped capabilities are available;
- `DISCOVERY_REQUIRED`: inspect more MCP tools before proceeding;
- `BLOCKED`: a required live-model capability is explicitly unavailable.

A blocked plan does not authorize a different bridge or arbitrary Fusion Python. Use an explicit manual Fusion step when acceptable, or keep the requirement unresolved.

### 4. Preserve the original design

Before material edits, use Fusion MCP to create a recoverable save, version, duplicate, or checkpoint. Record the document and checkpoint identity in `evidence.json`.

### 5. Build and inspect only through Fusion MCP

Use named parameters, descriptive components/bodies/features, separate components for separate physical parts, and fully constrained sketches where practical.

After each bounded phase, inspect the result before proceeding. For mechanisms, verify joint type, axis, limits, sampled positions, and interference through available Fusion MCP tools.

Read `references/mechanical-verification.md`.

### 6. Record live-model and engineering evidence

Create the ledger when needed:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" evidence-init `
  --contract "fusion-guardian\contract.json" `
  --out "fusion-guardian\evidence.json"
```

Statuses:

- `PASS`: checked and passed; method and concrete evidence required;
- `FAIL`: checked and failed; method and concrete evidence required;
- `NOT_VERIFIED`: adequate evidence was not collected;
- `NOT_APPLICABLE`: rationale required; a required check remains incomplete.

For multi-part contracts, part-specific evidence IDs are namespaced as `<part_id>.<requirement_id>`.

A screenshot proves appearance, not dimensions or mechanical function. “Looks correct” is not evidence.

Read `references/evidence-ledger.md`.

### 7. Export each final manufacturing candidate

Use Fusion MCP to export the exact intended body/component to STL in millimetres. If the connected MCP cannot export, use a one-time manual Fusion export and record that method explicitly.

Every export record should include:

- mesh path;
- SHA-256;
- part ID for multi-part contracts;
- component or body identity;
- Fusion document;
- checkpoint/version;
- export method.

Populate hashes after export:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" evidence-hash "fusion-guardian\evidence.json"
```

### 8. Audit exported STL files under resource limits

Single-part example:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" audit `
  "fusion-guardian\exports\camera-bracket.stl" `
  --contract "fusion-guardian\contract.json" `
  --json "fusion-guardian\reports\camera-bracket.json" `
  --markdown "fusion-guardian\reports\camera-bracket.md"
```

Multi-part example:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" audit `
  "fusion-guardian\exports\camera-bracket.stl" `
  --contract "fusion-guardian\contract.json" `
  --part-id camera_bracket `
  --json "fusion-guardian\reports\camera-bracket.json"
```

The auditor checks file identity, dimensions, topology, shells, triangle defects and quality, area, signed/absolute volume, uniform-density centre of mass, configured mass, build-plate contact, and orientation heuristics.

It also enforces preflight limits for file size, triangle count, coordinate magnitude, and estimated Python memory. A contract may tighten these limits but cannot silently loosen the CLI/default limits.

Read `references/resource-limits.md`.

Exit codes:

- `0`: successful audit or passing contract;
- `1`: geometric contract failure, blocked plan, regression, or failed gate;
- `2`: invalid input, invalid schema, resource-limit rejection, or execution error.

### 9. Compare revisions before accepting repairs

```powershell
py -3 "<skill-dir>\scripts\guardian.py" compare `
  "fusion-guardian\reports\before.json" `
  "fusion-guardian\reports\after.json" `
  --json "fusion-guardian\reports\regression.json" `
  --markdown "fusion-guardian\reports\regression.md"
```

Reports must represent the same part identity. Review topology, shell, defect, volume, area, and verdict regressions.

### 10. Repair with a bounded loop

Use no more than three automatic repair iterations unless the user requests more.

For each iteration:

1. isolate the smallest failed requirement;
2. edit only the relevant Fusion features through Fusion MCP;
3. repeat the relevant live-model check;
4. update the evidence ledger;
5. re-export only affected parts;
6. refresh export hashes;
7. rerun the matching part audits;
8. compare against the previous reports;
9. stop if the same unresolved failure repeats twice.

Do not regenerate the entire design when a local repair is sufficient.

### 11. Run the final acceptance gate

```powershell
py -3 "<skill-dir>\scripts\guardian.py" gate `
  --contract "fusion-guardian\contract.json" `
  --evidence "fusion-guardian\evidence.json" `
  --mesh-report "fusion-guardian\reports\camera-bracket.json" `
  --mesh-report "fusion-guardian\reports\sensor-cover.json" `
  --json "fusion-guardian\reports\acceptance.json" `
  --markdown "fusion-guardian\reports\acceptance.md"
```

The gate requires:

- passing required evidence;
- current contract-linked reports;
- SHA-256-matched export provenance;
- matching part identity;
- one current passing report for every required part.

Verdicts:

- `PASS`: all required evidence and all required part reports pass;
- `CONDITIONAL_PASS`: required checks pass, but optional engineering items remain;
- `INCOMPLETE`: required evidence, provenance, capability discovery, or a required part report is missing;
- `FAIL`: a required evidence or mesh check failed.

Read `references/acceptance-gate.md`.

## Validation and schemas

Guardian publishes JSON Schema Draft 2020-12 files in `schemas/` and performs strict dependency-free runtime validation.

```powershell
py -3 "<skill-dir>\scripts\guardian.py" validate contract contract.json
py -3 "<skill-dir>\scripts\guardian.py" validate evidence evidence.json
py -3 "<skill-dir>\scripts\guardian.py" validate capabilities capabilities.json
py -3 "<skill-dir>\scripts\guardian.py" validate audit-report report.json
```

Read `references/json-schemas.md`.

## Final reporting discipline

Always separate:

- **Observed through Fusion MCP**
- **Measured from exported mesh**
- **Established by calculation, simulation, slicer, or physical test**
- **Inferred**
- **Not verified**

A closed STL does not prove strength, wall thickness, joint correctness, continuous collision-free motion, print success, fit, or rules compliance. State those boundaries explicitly.
