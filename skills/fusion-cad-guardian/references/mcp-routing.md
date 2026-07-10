# MCP routing

## Always route to Fusion MCP

Subject to the connected server's actual capability profile:

- create, edit, suppress, or delete CAD objects;
- inspect the live model;
- save/version/checkpoint;
- move joints and inspect representative positions;
- run interference analysis;
- export final geometry.

## Always route to Guardian

- create and validate contracts;
- create and validate MCP capability profiles;
- generate a verification routing plan;
- create and validate evidence ledgers;
- hash and bind exported meshes;
- audit STL files under explicit resource limits;
- compare audit reports;
- run the final acceptance gate.

## Capability discovery

Do not assume tool names. Inspect the connected MCP server, record concrete tools or methods in `capabilities.json`, then run `guardian.py plan`.

## Do not use Guardian as a fallback CAD controller

If Fusion MCP lacks a required live operation:

1. state the missing capability;
2. use a supported manual Fusion step when reasonable;
3. record the manual method and evidence;
4. otherwise mark the check `NOT_VERIFIED`.

Do not silently install another Fusion bridge or execute arbitrary Fusion Python.
