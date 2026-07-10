# Fusion MCP capability profile

Guardian never assumes that every Fusion MCP server exposes the same tools.

Create a profile:

```powershell
py -3 scripts/guardian.py capabilities-init --out capabilities.json --server-name "Autodesk Fusion MCP"
```

Then inspect the connected MCP server's actual tool list and update one capability at a time:

```powershell
py -3 scripts/guardian.py capabilities-set capabilities.json export_stl available --tool "actual_export_tool_name"
py -3 scripts/guardian.py capabilities-set capabilities.json check_interference unavailable --notes "No interference tool exposed"
```

## Status meanings

- `available`: a concrete tool or method was observed. Record it.
- `unavailable`: the server was inspected and cannot perform the capability.
- `unknown`: discovery has not established whether the capability exists.

Marking a capability `available` requires a non-empty `tool` or `method`. A server name alone is not evidence.

## Planning

Generate a routing plan:

```powershell
py -3 scripts/guardian.py plan --contract contract.json --capabilities capabilities.json --json plan.json
```

The plan uses:

- `READY`: use the recorded Fusion MCP tool;
- `DISCOVER`: inspect the MCP server before continuing;
- `BLOCKED`: a required capability is explicitly unavailable;
- `OPTIONAL_EXTERNAL`: an optional requirement needs manual or external evidence;
- `REVIEW`: the requirement has no capability mapping and needs deliberate routing.

A blocked plan does not authorize Guardian to perform live CAD operations. Resolve it with another supported Fusion MCP operation, an explicit manual Fusion step, or a clearly recorded `NOT_VERIFIED` result.
