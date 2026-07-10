# Evidence ledger

The evidence ledger records claims that cannot be established from an STL alone.

## Statuses

- `PASS`: requirement was checked and passed. Method and concrete evidence are mandatory.
- `FAIL`: requirement was checked and failed. Method and concrete evidence are mandatory.
- `NOT_VERIFIED`: no adequate evidence was collected.
- `NOT_APPLICABLE`: a rationale is mandatory. A required requirement with this status leaves the gate incomplete.

## Sources

Use one of:

- `fusion_mcp`
- `calculation`
- `simulation`
- `slicer`
- `physical_test`
- `human_review`
- `other`

Viewport appearance is not sufficient evidence for a dimensional, joint, interference, or manufacturing claim.

## Multi-part evidence

Part-specific requirement IDs are namespaced as `<part_id>.<requirement_id>`, for example:

```json
{
  "id": "camera_bracket.critical_parameters",
  "part_id": "camera_bracket",
  "required": true,
  "status": "PASS",
  "method": "Fusion MCP parameter inspection",
  "evidence": "Mount spacing 40.00 mm and M3 hole diameter 3.20 mm in checkpoint V7",
  "source": "fusion_mcp"
}
```

Every multi-part export record must carry the same `part_id` used by its audit report.

## Good assembly evidence

```json
{
  "id": "interference_checked",
  "required": true,
  "status": "PASS",
  "method": "Fusion MCP interference analysis at 0°, 30°, 60° and 90° joint positions",
  "evidence": "No interference reported at sampled positions; minimum observed clearance 2.1 mm",
  "source": "fusion_mcp"
}
```

## Weak evidence

```json
{
  "id": "interference_checked",
  "status": "PASS",
  "method": "looked at it",
  "evidence": "seems fine",
  "source": "human_review"
}
```

Do not use weak evidence for required acceptance criteria.
