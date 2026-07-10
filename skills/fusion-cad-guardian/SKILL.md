---
name: fusion-cad-guardian
description: Work alongside Autodesk Fusion MCP to turn CAD requests into testable design contracts, record evidence from the live Fusion model, verify export provenance, audit final STL meshes, compare revisions, and issue an evidence-based acceptance verdict. Use for mechanical parts, assemblies, rover components, 3D-printable models, dimensional acceptance criteria, joint and interference evidence, exported-mesh quality, or bounded repair loops. This skill never replaces Fusion MCP and never performs live CAD editing itself.
---

# Fusion CAD Guardian

Fusion CAD Guardian is the **verification and acceptance layer** around a connected Autodesk Fusion MCP server.

- **Fusion MCP owns the live design:** create, edit, inspect, measure, move joints, check interference, save checkpoints, and export.
- **Guardian owns the process evidence:** requirements, evidence ledger, export identity, deterministic STL checks, regression comparison, and final acceptance gate.

Never route live Fusion operations through Guardian. Guardian runs dependency-free local Python outside Fusion and does not install an add-in or execute Python inside Fusion.

## Absolute capability boundary

| Task | Use |
|---|---|
| Create or modify sketches, bodies, features, components, parameters, joints | Fusion MCP |
| Inspect active document, units, feature health, dimensions, component structure | Fusion MCP |
| Test representative joint positions and interference | Fusion MCP |
| Export the intended body/component | Fusion MCP, or one-time manual export when unavailable |
| Define acceptance criteria | Guardian |
| Track how each requirement was verified | Guardian evidence ledger |
| Prove an audited STL is the recorded export | Guardian SHA-256 provenance |
| Audit STL topology, dimensions, volume, mass estimate, triangle quality, orientation heuristics | Guardian |
| Compare exported revisions for regressions | Guardian |
| Decide PASS / CONDITIONAL_PASS / INCOMPLETE / FAIL from collected evidence | Guardian gate |

Read `references/capability-boundaries.md` before making claims near the boundary.

## Required operating sequence

### 1. Inspect the connected Fusion MCP

Discover the actual MCP tools. Do not assume tool names or capabilities.

Confirm:

- Fusion is reachable;
- the active document and design context;
- the workspace and units;
- whether the task is a single part, multiple printable parts, or an assembly;
- whether the MCP can save/version, inspect parameters, test motion, check interference, and export STL.

If Fusion MCP is unavailable, Guardian may prepare a project or audit existing exports, but it must not imply that live-model checks occurred.

### 2. Create a Guardian project before editing

Use a project-local workspace:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" project "fusion-guardian" `
  --name "Rover Camera Bracket" `
  --task-type part
```

For an assembly, use `--task-type assembly`.

The command creates:

```text
fusion-guardian/
├── TASK.md
├── contract.json
├── evidence.json
├── batch.json
├── exports/
├── reports/
└── snapshots/
```

### 3. Replace placeholders with a measurable contract

Edit `contract.json` before making geometry.

Separate requirements into:

1. **Fusion requirements** — facts available only from the live parametric design, such as named parameters, sketch constraints, feature health, component structure, joint axes/limits, representative motion, and interference.
2. **Mesh requirements** — facts measurable from the exported STL, such as overall dimensions, manifoldness, shells, triangle defects, volume, estimated mass, build-plate contact, and orientation heuristics.
3. **Engineering requirements** — material, loads, torque, safety factor, tolerances, shrinkage, fastening strategy, simulation, slicer review, and physical testing.

Do not invent a critical mechanical requirement silently. Record assumptions in the contract notes.

Validate the contract:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" validate contract "fusion-guardian\contract.json"
```

Read `references/design-contract.md` for the schema.

### 4. Preserve the original model

Before significant edits, use Fusion MCP to create a safe checkpoint through a save, version, duplicate, or explicit copy. Record the method in `evidence.json` under `safe_checkpoint`.

Do not continue destructive work without a recoverable state unless the user explicitly accepts that risk.

### 5. Build and inspect through Fusion MCP

Use short, testable phases:

1. named parameters and component plan;
2. constrained primary sketches;
3. base features;
4. interfaces, holes, clearances, and mounting geometry;
5. assembly relationships and joints;
6. semantic inspection;
7. export.

After each phase, inspect before proceeding. Prefer local repairs over full regeneration.

For assemblies, read `references/mechanical-verification.md` and sample neutral, extreme, and representative intermediate positions. A mechanism is not verified merely because its components exist.

### 6. Populate the evidence ledger

Every Fusion or engineering requirement must have one of:

- `PASS`
- `FAIL`
- `NOT_VERIFIED`
- `NOT_APPLICABLE`

A `PASS` or `FAIL` must include:

- the method used;
- concrete evidence;
- a source such as `fusion_mcp`, `calculation`, `simulation`, `slicer`, `physical_test`, or `human_review`.

A required check marked `NOT_APPLICABLE` is treated as incomplete; remove or make the requirement optional instead of bypassing it.

Validate the ledger:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" validate evidence "fusion-guardian\evidence.json"
```

Read `references/evidence-ledger.md`.

### 7. Export and record provenance

Export only the intended final candidate body/component into `exports/`. Use descriptive file names and millimetres.

For each export, add an entry to `evidence.json` containing:

- mesh path;
- component or body;
- Fusion document;
- checkpoint/version;
- export method.

Then populate hashes:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" evidence-hash "fusion-guardian\evidence.json"
```

Guardian will not accept an audited mesh as the Fusion export unless its SHA-256 matches a complete provenance record.

### 8. Audit every final STL

```powershell
py -3 "<skill-dir>\scripts\guardian.py" audit `
  "fusion-guardian\exports\camera-bracket.stl" `
  --contract "fusion-guardian\contract.json" `
  --json "fusion-guardian\reports\camera-bracket.mesh.json" `
  --markdown "fusion-guardian\reports\camera-bracket.mesh.md"
```

The audit checks configured criteria including:

- bounding-box dimensions;
- closed-manifold indicators;
- boundary and non-manifold edges;
- shells;
- degenerate, duplicate, and inconsistent-winding triangles;
- sliver count and triangle quality;
- surface area and signed/absolute volume;
- uniform-density centre of mass;
- optional mass estimate from density;
- optional build-plate contact;
- optional severe downward-facing area heuristic.

The report embeds both the STL SHA-256 and the contract SHA-256.

An audit without `--contract` is `AUDIT_ONLY` and cannot satisfy the final gate.

### 9. Compare risky revisions

Audit before and after exports, then run:

```powershell
py -3 "<skill-dir>\scripts\guardian.py" compare `
  "fusion-guardian\reports\before.mesh.json" `
  "fusion-guardian\reports\after.mesh.json" `
  --json "fusion-guardian\reports\regression.json" `
  --markdown "fusion-guardian\reports\regression.md"
```

Treat increased boundary edges, non-manifold edges, shells, degenerates, duplicates, winding errors, or slivers as regressions unless explicitly justified.

### 10. Run the acceptance gate

```powershell
py -3 "<skill-dir>\scripts\guardian.py" gate `
  --contract "fusion-guardian\contract.json" `
  --evidence "fusion-guardian\evidence.json" `
  --mesh-report "fusion-guardian\reports\camera-bracket.mesh.json" `
  --json "fusion-guardian\reports\acceptance.json" `
  --markdown "fusion-guardian\reports\acceptance.md"
```

Repeat `--mesh-report` for multiple exported parts.

Gate meanings:

- `PASS` — all required live-model evidence passes, every mesh report passes the current contract, export provenance matches, and no optional engineering checks remain open.
- `CONDITIONAL_PASS` — all required automated/live checks pass, but optional engineering or physical checks remain open.
- `INCOMPLETE` — required evidence, current-contract mesh reports, or export provenance is missing.
- `FAIL` — at least one required evidence item or mesh contract check fails.

Read `references/acceptance-gate.md`.

## Repair policy

Use at most three autonomous repair iterations unless the user asks for more.

For each iteration:

1. select the smallest failed requirement;
2. change only the relevant Fusion features through MCP;
3. rerun the applicable live-model check;
4. update evidence;
5. re-export the affected body/component;
6. repopulate export hashes;
7. rerun its mesh audit;
8. compare against the previous export;
9. rerun the gate.

Stop when:

- the gate passes;
- the same failure repeats twice;
- a required operation is unavailable;
- the fix requires an unapproved engineering assumption;
- further modification risks the original design.

## Claim discipline

Never claim that Guardian proves:

- minimum wall thickness;
- local hole position or fit tolerances;
- continuous collision-free motion;
- structural strength or safety factor;
- material suitability;
- print shrinkage or dimensional accuracy;
- slicer support requirements;
- competition rules compliance.

These require Fusion inspection, measurement, simulation, calculations, slicer analysis, physical testing, or human review. Record them as evidence when actually performed; otherwise keep them `NOT_VERIFIED`.

## Final response format

Report:

1. document and checkpoint examined;
2. contract and assumptions;
3. Fusion MCP checks and evidence;
4. exported files and matching hashes;
5. mesh audit results;
6. regressions and repairs;
7. acceptance-gate verdict;
8. all remaining unverified or optional engineering items.

Never collapse `CONDITIONAL_PASS` or `INCOMPLETE` into “done.”

## Commands

```powershell
# Create a project
py -3 "<skill-dir>\scripts\guardian.py" project project-dir --name "Part" --task-type part

# Create only a contract
py -3 "<skill-dir>\scripts\guardian.py" init --out contract.json --part-name "Part"

# Create an evidence ledger from an existing contract
py -3 "<skill-dir>\scripts\guardian.py" evidence-init --contract contract.json --out evidence.json

# Populate export hashes
py -3 "<skill-dir>\scripts\guardian.py" evidence-hash evidence.json

# Validate JSON
py -3 "<skill-dir>\scripts\guardian.py" validate contract contract.json
py -3 "<skill-dir>\scripts\guardian.py" validate evidence evidence.json

# Audit, compare, batch, and gate
py -3 "<skill-dir>\scripts\guardian.py" audit part.stl --contract contract.json
py -3 "<skill-dir>\scripts\guardian.py" compare before.json after.json
py -3 "<skill-dir>\scripts\guardian.py" batch batch.json --out-dir reports
py -3 "<skill-dir>\scripts\guardian.py" gate --contract contract.json --evidence evidence.json --mesh-report report.json

# Installation health check
py -3 "<skill-dir>\scripts\guardian.py" self-test
```

On Windows, `scripts/guardian.ps1` locates `py -3` or `python` and forwards arguments.
