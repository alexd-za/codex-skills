# codex-skills

Custom Codex skills, scripts, and reusable agent workflows.

## Available skills

### Fusion CAD Guardian — v2.2.0

A verification and manufacturing-evidence layer that works **alongside Autodesk Fusion MCP**. Fusion MCP remains responsible for every live CAD operation; Guardian adds capability-aware design contracts, evidence tracking, export provenance, multi-part completeness, resource-limited STL/core-3MF auditing, source-linked G-code metadata, HTML reports, regression comparison, integrity bundles, and final acceptance gates.

Install with Codex:

```text
$skill-installer install https://github.com/alexd-za/codex-skills/tree/main/skills/fusion-cad-guardian
```

Restart Codex and verify locally:

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" doctor
```

[Open the skill directory](./skills/fusion-cad-guardian)

## Release history

- **v2.2.0** — core 3MF, existing-G-code evidence, HTML reports, integrity bundles, migration/doctor tooling, and archive hardening.
- **v2.1.0** — JSON Schemas, MCP capability profiles, resource limits, and first-class multi-part verification.
- **v2.0.0** — evidence ledger, export provenance, enhanced mesh analysis, and acceptance gate.
- **v1.0.0** — initial STL audit and design-contract workflow.

## Licence

MIT
