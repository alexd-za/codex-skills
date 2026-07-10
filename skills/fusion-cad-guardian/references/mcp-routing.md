# MCP routing

## Always route to Fusion MCP

- create, edit, suppress or delete CAD objects;
- inspect the live model;
- save/version/checkpoint;
- move joints and test representative positions;
- run interference analysis;
- export final geometry.

## Always route to Guardian

- create/validate contracts;
- create/validate evidence ledgers;
- hash and bind exported meshes;
- audit STL files;
- compare audit reports;
- run the final acceptance gate.

## Do not use Guardian as a fallback CAD controller

If Fusion MCP lacks a required live operation:

1. state the missing capability;
2. use a supported manual Fusion step when reasonable;
3. record the manual method and evidence;
4. otherwise mark the check `NOT_VERIFIED`.

Do not silently install another Fusion bridge or execute arbitrary Fusion Python.
