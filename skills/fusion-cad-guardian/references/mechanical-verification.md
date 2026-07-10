# Mechanical verification

## Part checks

Use Fusion MCP to verify:

- named critical dimensions and parameters;
- mounting-hole diameters and spacing;
- body/component identity;
- feature health;
- intended export selection;
- clearances that depend on local geometry.

Use Guardian only for export-level checks.

## Assembly and mechanism checks

At minimum:

1. verify component grounding and intended degrees of freedom;
2. verify joint type, axis, orientation and limits;
3. inspect neutral and both extreme positions;
4. inspect representative intermediate positions;
5. run interference at each sampled position;
6. record minimum clearance where the MCP can measure it;
7. identify collisions that could occur between samples as unresolved unless continuous analysis is available.

STL reports cannot prove assembly motion or joint correctness.

## Engineering checks

Loads, material, servo torque, fastener capacity, fatigue, impact, thermal effects and safety factors require calculations, simulation, references, or physical tests. Record the method and evidence rather than inferring them from geometry.
