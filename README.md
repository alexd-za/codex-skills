# codex-skills

Custom Codex skills, scripts, and reusable agent workflows.

## Available skills

### Fusion CAD Guardian — v2.1.0

A verification and acceptance layer that works **alongside Autodesk Fusion MCP**. Fusion MCP remains responsible for every live CAD operation; Guardian adds design contracts, capability routing, evidence tracking, export provenance, multi-part completeness, deterministic STL auditing, resource limits, regression comparison, and final acceptance gates.

Install with Codex:

```text
$skill-installer install https://github.com/alexd-za/codex-skills/tree/main/skills/fusion-cad-guardian
```

Then restart Codex and verify locally:

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" self-test
```

[Open the skill directory](./skills/fusion-cad-guardian)

## Release history

- **v2.1.0** — JSON Schemas, MCP capability profiles, resource limits, and first-class multi-part verification.
- **v2.0.0** — evidence ledger, export provenance, enhanced mesh analysis, and acceptance gate.
- **v1.0.0** — initial STL audit and design-contract workflow.

## Licence

MIT
