# Multi-part contracts

Use one project contract when several exported bodies belong to the same Fusion design or assembly.

Create a project with named parts:

```powershell
py -3 scripts/guardian.py project guardian-project `
  --name "Rover Camera Mount" `
  --task-type assembly `
  --part "camera_bracket=Camera Bracket" `
  --part "sensor_cover=Sensor Cover"
```

Or add a part to an existing contract:

```powershell
py -3 scripts/guardian.py part-add contract.json --id camera_bracket --name "Camera Bracket"
```

When `parts` is non-empty:

- top-level `mesh` must be empty;
- every part has its own mesh contract;
- evidence IDs are namespaced as `<part_id>.<requirement_id>`;
- each export record must include `part_id`;
- each audit must specify `--part-id` when more than one part exists;
- the final gate requires one passing, current, provenance-linked report for every required part.

Example audit:

```powershell
py -3 scripts/guardian.py audit exports/camera-bracket.stl `
  --contract contract.json `
  --part-id camera_bracket `
  --json reports/camera-bracket.json
```

Do not combine several printable parts into one STL merely to satisfy the gate. Audit each intended manufacturing output independently.
