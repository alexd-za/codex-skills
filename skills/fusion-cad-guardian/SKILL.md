---
name: fusion-cad-guardian
description: Verify Autodesk Fusion work alongside a connected Fusion MCP. Use for capability-aware CAD plans, evidence-led acceptance criteria, STL/3MF audits, G-code metadata evidence, export provenance, multi-part gates, regression reports, and integrity bundles. Never use it to edit the live Fusion model or replace Fusion MCP.
---

# Fusion CAD Guardian 2.2

Guardian is the **planning, evidence, exported-file, and acceptance layer** around Fusion MCP.

- **Fusion MCP owns the live design:** inspect, create, edit, measure, checkpoint, test joints, check interference, and export.
- **Guardian owns verification discipline:** contracts, capability routing, evidence, provenance, STL/3MF analysis, optional G-code metadata, regression comparison, reports, bundles, and the final gate.

Guardian runs standard-library Python outside Fusion. It does not install an add-in, call Fusion APIs, execute arbitrary Python inside Fusion, or launch a slicer.

## Non-negotiable boundary

| Operation | Owner |
|---|---|
| Modify or inspect live Fusion geometry | Fusion MCP |
| Save/version/checkpoint the design | Fusion MCP |
| Test joints and interference | Fusion MCP |
| Export the intended body/component | Fusion MCP or an explicitly recorded manual Fusion export |
| Define measurable requirements | Guardian contract |
| Record verification evidence | Guardian evidence ledger |
| Audit STL/core 3MF and existing G-code | Guardian scripts |
| Issue the evidence-based verdict | Guardian gate |

Never route live-CAD actions through Guardian. A missing MCP capability remains `BLOCKED`, `DISCOVERY_REQUIRED`, or an explicit manual/external step.

Read `references/capability-boundaries.md` before making claims near this boundary.

## Required workflow

### 1. Inspect and profile the connected MCP

Discover the actual tools. Do not assume tool names from documentation or another server.

```powershell
py -3 "<skill-dir>\scripts\guardian.py" capabilities-init `
  --out "fusion-guardian\capabilities.json" `
  --server-name "Autodesk Fusion MCP"
```

Mark a capability `available` only with a concrete tool or method:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" capabilities-set `
  "fusion-guardian\capabilities.json" inspect_component_structure available `
  --tool "<observed-tool-name>"
```

Use `unknown` while discovery is incomplete and `unavailable` only after inspection confirms absence. Read `references/capability-profile.md`.

### 2. Create the contract before editing

```powershell
py -3 "<skill-dir>\scripts\guardian.py" project "fusion-guardian" `
  --name "Rover Camera Mount" `
  --task-type assembly `
  --part "camera_bracket=Camera Bracket" `
  --part "sensor_cover=Sensor Cover"
```

The contract must separate:

- live Fusion requirements;
- assembly/mechanism requirements;
- per-part exported-mesh requirements;
- optional slicer metadata requirements;
- external engineering, simulation, physical-test, and human-review requirements;
- resource limits for untrusted inputs.

Do not invent critical dimensions, loads, materials, fits, or safety factors. State assumptions. Read `references/design-contract.md` and `references/multi-part.md`.

### 3. Generate the capability-aware plan

```powershell
py -3 "<skill-dir>\scripts\guardian.py" plan `
  --contract "fusion-guardian\contract.json" `
  --capabilities "fusion-guardian\capabilities.json" `
  --json "fusion-guardian\plan.json"
```

Interpret `READY`, `DISCOVERY_REQUIRED`, and `BLOCKED` literally. Do not bypass a blocker with another bridge or generated Fusion Python.

### 4. Checkpoint, build, and inspect through Fusion MCP

Before material edits, create a recoverable checkpoint. Use Fusion MCP for every live-model operation. Prefer named parameters, descriptive components/bodies/features, separate physical components, and constrained sketches.

After each bounded phase, inspect the live result. For mechanisms, record joint type, axis, limits, sampled poses, and interference results. Read `references/mechanical-verification.md`.

### 5. Record evidence and export provenance

```powershell
py -3 "<skill-dir>\scripts\guardian.py" evidence-init `
  --contract "fusion-guardian\contract.json" `
  --out "fusion-guardian\evidence.json"
```

Evidence statuses:

- `PASS`: checked and passed; method and concrete evidence required.
- `FAIL`: checked and failed; method and concrete evidence required.
- `NOT_VERIFIED`: evidence was not collected.
- `NOT_APPLICABLE`: rationale required; a required check remains incomplete.

A screenshot proves appearance, not dimensions or mechanical function.

Record the selected part/body, Fusion document, checkpoint/version, export method, file path, and SHA-256. Then run:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" evidence-hash "fusion-guardian\evidence.json"
```

Read `references/evidence-ledger.md`.

### 6. Audit the exported manufacturing candidate

STL and core 3MF are supported. For a 3MF with multiple build objects, inspect and select the intended object explicitly:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" inspect-3mf "fusion-guardian\exports\assembly.3mf"

py -3 "<skill-dir>\scripts\guardian.py" audit `
  "fusion-guardian\exports\assembly.3mf" `
  --object-name "Camera Bracket" `
  --contract "fusion-guardian\contract.json" `
  --part-id camera_bracket `
  --json "fusion-guardian\reports\camera-bracket.json" `
  --markdown "fusion-guardian\reports\camera-bracket.md" `
  --html "fusion-guardian\reports\camera-bracket.html"
```

Do not claim support for advanced 3MF material, texture, beam-lattice, slice, or vendor extensions. Read `references/3mf-and-slicer.md` and `references/resource-limits.md`.

### 7. Add slicer evidence only when an existing G-code file is available

Guardian parses common metadata comments but never runs a slicer:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" slicer-audit `
  "fusion-guardian\gcode\camera-bracket.gcode" `
  --source-mesh "fusion-guardian\exports\camera-bracket.3mf" `
  --contract "fusion-guardian\contract.json" `
  --part-id camera_bracket `
  --json "fusion-guardian\reports\camera-bracket.slicer.json"
```

The source mesh hash must match the current mesh report when the contract requires it. Missing metadata remains unresolved; never substitute zero.

### 8. Repair only failed requirements

Use a bounded loop, normally no more than three iterations:

1. identify the failed requirement IDs;
2. make the smallest targeted change through Fusion MCP;
3. save a new checkpoint;
4. re-inspect live evidence;
5. re-export;
6. refresh hashes;
7. rerun affected mesh/slicer checks;
8. compare revisions.

```powershell
py -3 "<skill-dir>\scripts\guardian.py" compare before.json after.json `
  --json regression.json --html regression.html
```

### 9. Run the final gate

```powershell
py -3 "<skill-dir>\scripts\guardian.py" gate `
  --contract "fusion-guardian\contract.json" `
  --evidence "fusion-guardian\evidence.json" `
  --mesh-report "fusion-guardian\reports\camera-bracket.json" `
  --slicer-report "fusion-guardian\reports\camera-bracket.slicer.json" `
  --json "fusion-guardian\reports\acceptance.json" `
  --html "fusion-guardian\reports\acceptance.html"
```

Verdicts:

- `PASS`: every required evidence source passes and provenance is current.
- `CONDITIONAL_PASS`: required checks pass; optional checks remain unresolved.
- `INCOMPLETE`: required evidence, part reports, provenance, or required slicer evidence is missing/stale.
- `FAIL`: a required check failed.

Read `references/acceptance-gate.md`.

### 10. Preserve the evidence package

```powershell
py -3 "<skill-dir>\scripts\guardian.py" bundle `
  --project "fusion-guardian" `
  --out "fusion-guardian\bundles\verification.zip"

py -3 "<skill-dir>\scripts\guardian.py" bundle-verify `
  "fusion-guardian\bundles\verification.zip"
```

Read `references/verification-bundles.md`.

## Claim discipline

Guardian does not prove local wall thickness, minimum clearance, joint correctness, continuous collision-free motion, strength, fatigue, print success, material suitability, or rules compliance. Require Fusion MCP evidence, calculation, simulation, slicer inspection, physical testing, or human engineering review as appropriate.

Before long-term use, run `doctor`. Use `migrate` when upgrading an existing schema-version 2 contract to revision 2.2.
