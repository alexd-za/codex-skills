# Fusion CAD Guardian

**Current release: v2.0.0**

Fusion CAD Guardian is a Codex skill that works alongside Autodesk Fusion MCP. It does not create or edit CAD itself. Fusion MCP remains the live-design controller; Guardian supplies the requirements, evidence, export provenance, deterministic STL auditing, regression comparison, and final acceptance gate that a generic MCP connection does not provide automatically.

## Division of responsibility

```text
Codex
├── Autodesk Fusion MCP
│   ├── creates and modifies the parametric model
│   ├── inspects components, parameters, sketches and features
│   ├── tests joints, motion and interference
│   ├── saves checkpoints
│   └── exports final bodies/components
└── Fusion CAD Guardian
    ├── creates a measurable design contract
    ├── records evidence from MCP/calculation/simulation/testing
    ├── binds exports to Fusion checkpoints with SHA-256
    ├── audits final STL geometry deterministically
    ├── compares revisions for mesh regressions
    └── produces PASS / CONDITIONAL_PASS / INCOMPLETE / FAIL
```

Guardian never installs a Fusion add-in and never executes arbitrary Python inside Fusion.

## Install

In Codex:

```text
$skill-installer install https://github.com/alexd-za/codex-skills/tree/main/skills/fusion-cad-guardian
```

Restart Codex, then verify from native Windows PowerShell:

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" self-test
```

## Start a project

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" project `
  ".\fusion-guardian" `
  --name "Rover Camera Bracket" `
  --task-type part
```

Then tell Codex:

```text
Use $fusion-cad-guardian alongside my connected Autodesk Fusion MCP.
Use Fusion MCP for every live CAD action. Use Guardian to define the contract,
record evidence, bind the exported STL to the Fusion checkpoint, audit it, and
run the final acceptance gate. Do not claim unverified engineering properties.
```

## v2.0.0 highlights

- schema-v2 contracts with separate Fusion, mesh, and engineering requirements;
- complete project scaffolding;
- validated evidence ledger;
- export provenance tied to STL SHA-256, document, checkpoint, and body/component;
- contract SHA-256 embedded in mesh reports;
- acceptance gate rejects audit-only, stale-contract, or untraceable meshes;
- STL checks for dimensions, topology, shells, volume, surface area, centre of mass, triangle quality, slivers, optional mass, build-plate contact, and orientation heuristics;
- before/after regression reports;
- legacy schema-v1 contract compatibility;
- dependency-free Python 3.10+ implementation.

## Requirements

- native Windows Codex;
- Autodesk Fusion with a connected Fusion MCP server for live-model operations;
- Python 3.10+ for local verification;
- final STL exports in millimetres.

No pip packages are required.

## Important limits

STL analysis cannot prove joint motion, interference, component relationships, wall thickness, local tolerances, structural strength, material suitability, print shrinkage, slicer supports, or competition compliance. Guardian forces these claims into explicit evidence checks instead of pretending they were verified.

See [CHANGELOG.md](CHANGELOG.md) for release history.
