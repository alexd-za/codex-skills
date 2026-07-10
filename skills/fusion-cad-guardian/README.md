# Fusion CAD Guardian 2.2.0

A Codex skill that works **alongside Autodesk Fusion MCP** as a verification, manufacturing-evidence, and acceptance layer.

Fusion MCP remains the sole controller of the live Fusion design. Guardian adds:

- single-part and multi-part design contracts;
- capability-aware routing against the connected Fusion MCP;
- structured Fusion, engineering, and manufacturing evidence;
- SHA-256 export provenance;
- resource-limited STL and core 3MF auditing;
- source-linked G-code/slicer metadata evidence;
- revision comparison and regression detection;
- standalone JSON, Markdown, and HTML reports;
- integrity-checked verification bundles;
- a final `PASS`, `CONDITIONAL_PASS`, `INCOMPLETE`, or `FAIL` gate.

Guardian does **not** edit Fusion, install an add-in, execute Fusion Python, run a slicer, or claim that exported-file analysis proves mechanical performance.

## Install

```text
$skill-installer install https://github.com/alexd-za/codex-skills/tree/main/skills/fusion-cad-guardian
```

Restart Codex after installation.

## Requirements

- Codex with local skill/script execution;
- Autodesk Fusion with a connected Fusion MCP server for live-CAD work;
- Python 3.10 or newer;
- STL or core 3MF exports for deterministic mesh checks;
- optional existing G-code for slicer evidence.

The runtime uses only the Python standard library. CI optionally installs `jsonschema` to validate the published schemas.

## Verify the installation

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" doctor
```

Run the focused self-test:

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" self-test
```

## Recommended workflow

### 1. Create a project

```powershell
py -3 .\scripts\guardian.py project .\guardian-project `
  --name "Rover Camera Mount" `
  --task-type assembly `
  --part "camera_bracket=Camera Bracket" `
  --part "sensor_cover=Sensor Cover"
```

### 2. Profile the actual Fusion MCP

```powershell
py -3 .\scripts\guardian.py capabilities-set `
  .\guardian-project\capabilities.json inspect_component_structure available `
  --tool "<actual-connected-tool-name>"

py -3 .\scripts\guardian.py plan `
  --contract .\guardian-project\contract.json `
  --capabilities .\guardian-project\capabilities.json `
  --json .\guardian-project\plan.json
```

Guardian never guesses tool availability from a server name.

### 3. Build, inspect, checkpoint, and export through Fusion MCP

Use Fusion MCP for all live-model actions. Record concrete evidence in `evidence.json`, including the Fusion document, checkpoint/version, selected component/body, export method, and generated file.

### 4. Audit STL or 3MF

STL:

```powershell
py -3 .\scripts\guardian.py audit `
  .\guardian-project\exports\camera-bracket.stl `
  --contract .\guardian-project\contract.json `
  --part-id camera_bracket `
  --json .\guardian-project\reports\camera-bracket.json `
  --markdown .\guardian-project\reports\camera-bracket.md `
  --html .\guardian-project\reports\camera-bracket.html
```

3MF with multiple build objects:

```powershell
py -3 .\scripts\guardian.py inspect-3mf .\guardian-project\exports\assembly.3mf

py -3 .\scripts\guardian.py audit `
  .\guardian-project\exports\assembly.3mf `
  --object-name "Camera Bracket" `
  --contract .\guardian-project\contract.json `
  --part-id camera_bracket `
  --json .\guardian-project\reports\camera-bracket.json
```

Guardian supports the core 3MF mesh/component/build model, transforms, and standard units. It does not interpret advanced material, texture, beam-lattice, slice, or vendor-specific extensions.

### 5. Import optional slicer evidence

Guardian parses an **existing** G-code file. It never launches or controls a slicer.

```powershell
py -3 .\scripts\guardian.py slicer-audit `
  .\guardian-project\gcode\camera-bracket.gcode `
  --source-mesh .\guardian-project\exports\camera-bracket.3mf `
  --contract .\guardian-project\contract.json `
  --part-id camera_bracket `
  --json .\guardian-project\reports\camera-bracket.slicer.json `
  --html .\guardian-project\reports\camera-bracket.slicer.html
```

Recognized metadata includes common generator, estimated-time, filament, layer, nozzle, and maximum-Z comments. Missing metadata remains missing; it is never treated as zero.

### 6. Run the acceptance gate

```powershell
py -3 .\scripts\guardian.py gate `
  --contract .\guardian-project\contract.json `
  --evidence .\guardian-project\evidence.json `
  --mesh-report .\guardian-project\reports\camera-bracket.json `
  --mesh-report .\guardian-project\reports\sensor-cover.json `
  --slicer-report .\guardian-project\reports\camera-bracket.slicer.json `
  --json .\guardian-project\reports\acceptance.json `
  --html .\guardian-project\reports\acceptance.html
```

### 7. Create an integrity bundle

```powershell
py -3 .\scripts\guardian.py bundle `
  --project .\guardian-project `
  --out .\guardian-project\bundles\camera-mount-verification.zip

py -3 .\scripts\guardian.py bundle-verify `
  .\guardian-project\bundles\camera-mount-verification.zip
```

The bundle contains a manifest with the size and SHA-256 of every included file. Verification is streamed and subject to archive resource limits.

## v2.2 highlights

- Core 3MF auditing with unit conversion, components, build items, transforms, and explicit object selection.
- ZIP/XML defenses for 3MF and bundle inputs: path traversal, encrypted members, entry count, expanded size, compression ratio, DTD/entity declarations, transform cycles, and resource limits.
- Existing-G-code metadata evidence linked to the exact source mesh SHA-256.
- Optional slicer acceptance criteria integrated into single-part and multi-part gates.
- Standalone escaped HTML reports for audit, slicer, comparison, and acceptance outputs.
- Integrity bundles with streamed creation/verification and tamper detection.
- `doctor` for package/project diagnostics and `migrate` for v2 contract revision upgrades.
- Seven Draft 2020-12 JSON Schemas.
- 41 dependency-free unit tests plus schema-conformance CI.

## Critical limitations

Guardian can verify file identity, global dimensions, topology indicators, shell counts, triangle defects, surface area, volume, uniform-density centre of mass, configured mass, build-plane contact, orientation heuristics, and selected slicer metadata.

Guardian cannot prove:

- that the correct feature was modeled unless Fusion evidence identifies it;
- local wall thickness or minimum clearance from its global mesh audit;
- joint definitions or continuous collision-free motion;
- strength, fatigue life, impact resistance, thermal performance, or material suitability;
- slicer correctness or physical print success;
- competition, regulatory, or safety compliance.

Those require Fusion MCP evidence, engineering calculation, simulation, slicer inspection, physical testing, or human review.
