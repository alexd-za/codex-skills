# Fusion CAD Guardian 2.1.0

A Codex skill that works **alongside Autodesk Fusion MCP** as a verification and acceptance layer.

Fusion MCP controls the live Fusion design. Guardian adds:

- explicit single-part and multi-part design contracts;
- a capability profile for the connected Fusion MCP server;
- capability-aware verification planning without assuming tool names;
- structured Fusion, engineering, and manufacturing evidence;
- SHA-256 export provenance;
- resource-limited deterministic STL auditing;
- before/after regression detection;
- a final `PASS`, `CONDITIONAL_PASS`, `INCOMPLETE`, or `FAIL` gate.

Guardian never edits Fusion, installs an add-in, or executes arbitrary Python inside Fusion.

## Install

```text
$skill-installer install https://github.com/alexd-za/codex-skills/tree/main/skills/fusion-cad-guardian
```

Restart Codex after installation.

## Requirements

- native Windows Codex;
- Autodesk Fusion with a connected Fusion MCP server;
- Python 3.10 or newer for local verification scripts;
- STL exports in millimetres.

No third-party Python packages are required.

## Verify

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" self-test
```

## v2.1 additions

### Formal JSON Schemas

Draft 2020-12 schemas are included for contracts, evidence ledgers, export records, capability profiles, and audit reports. Runtime validation remains dependency-free.

### Fusion MCP capability profile

Guardian records which capabilities the connected server actually exposes. It requires a concrete tool or method before marking a capability available and can produce a routing plan showing `READY`, `DISCOVERY_REQUIRED`, or `BLOCKED` requirements.

### Mesh resource limits

Before loading an STL, Guardian checks:

- file size;
- declared or observed triangle count;
- coordinate magnitude;
- estimated Python analysis memory.

Contracts may tighten these limits but cannot silently loosen runtime limits.

### Multi-part contracts

A single contract can define several required manufacturing outputs. Each part receives:

- a stable `part_id`;
- its own mesh acceptance criteria;
- namespaced evidence requirements;
- part-linked export provenance;
- a required current report at the final gate.

## Create a multi-part project

```powershell
py -3 .\scripts\guardian.py project .\guardian-project `
  --name "Rover Camera Mount" `
  --task-type assembly `
  --part "camera_bracket=Camera Bracket" `
  --part "sensor_cover=Sensor Cover"
```

This creates:

```text
guardian-project/
├── contract.json
├── evidence.json
├── capabilities.json
├── batch.json
├── TASK.md
├── exports/
├── reports/
└── snapshots/
```

## Profile the connected Fusion MCP

```powershell
py -3 .\scripts\guardian.py capabilities-set `
  .\guardian-project\capabilities.json export_stl available `
  --tool "<actual-connected-tool-name>"

py -3 .\scripts\guardian.py plan `
  --contract .\guardian-project\contract.json `
  --capabilities .\guardian-project\capabilities.json `
  --json .\guardian-project\plan.json
```

Guardian does not infer tool availability from server names.

## Audit each exported part

```powershell
py -3 .\scripts\guardian.py audit `
  .\guardian-project\exports\camera-bracket.stl `
  --contract .\guardian-project\contract.json `
  --part-id camera_bracket `
  --json .\guardian-project\reports\camera-bracket.json `
  --markdown .\guardian-project\reports\camera-bracket.md
```

## Run the final gate

```powershell
py -3 .\scripts\guardian.py gate `
  --contract .\guardian-project\contract.json `
  --evidence .\guardian-project\evidence.json `
  --mesh-report .\guardian-project\reports\camera-bracket.json `
  --mesh-report .\guardian-project\reports\sensor-cover.json `
  --json .\guardian-project\reports\acceptance.json
```

## Capability boundary

Guardian can verify exported mesh identity, overall dimensions, topology indicators, shells, triangle defects, surface area, volume, uniform-density centre of mass, configured mass, build-plane contact, and orientation heuristics.

It cannot prove joint definitions, continuous collision-free motion, local clearances, minimum wall thickness, strength, fatigue, print success, material suitability, or rules compliance. Those require Fusion MCP evidence, calculation, simulation, slicer analysis, physical testing, or human engineering review.
