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

## Good evidence

```json
{
  "id": "interference_checked",
  "required": true,
  "status": "PASS",
  "method": "Fusion MCP interference analysis at 0°, 30°, 60° and 90° joint positions",
  "evidence": "No interference reported at all sampled positions; minimum observed clearance 2.1 mm",
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
