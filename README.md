# Codex Skills

Custom Codex skills, scripts, and reusable agent workflows maintained by Alex.

## Available skills

### Fusion CAD Guardian — v2.0.0

A verification and acceptance layer that works **alongside Autodesk Fusion MCP**.

Fusion MCP remains responsible for all live CAD creation, editing, inspection, motion, interference checks, checkpoints, and exports. Guardian adds:

- measurable design contracts;
- evidence ledgers for Fusion, engineering, simulation, slicer, and physical checks;
- STL export provenance tied to Fusion document/checkpoint metadata and SHA-256;
- deterministic STL audits;
- before/after mesh-regression reports;
- a final `PASS`, `CONDITIONAL_PASS`, `INCOMPLETE`, or `FAIL` acceptance gate.

[View Fusion CAD Guardian](skills/fusion-cad-guardian/)

## Install

In Codex:

```text
$skill-installer install https://github.com/alexd-za/codex-skills/tree/main/skills/fusion-cad-guardian
```

Restart Codex, then run:

```powershell
py -3 "$HOME\.agents\skills\fusion-cad-guardian\scripts\guardian.py" self-test
```

## Release history

- **v1.0.0** — initial design-contract and STL-audit release.
- **v2.0.0** — evidence ledger, export provenance, contract-linked reports, acceptance gate, improved mesh analysis, project scaffolding, and stricter Fusion-MCP capability boundaries.

See the skill's [changelog](skills/fusion-cad-guardian/CHANGELOG.md) for details.
