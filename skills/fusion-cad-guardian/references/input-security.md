# Input security

Treat STL, 3MF, G-code, contracts, evidence files, reports, and bundles as untrusted inputs.

Guardian is deliberately dependency-free and does not execute input content. It still applies limits because malformed or highly compressed data can exhaust memory or CPU.

## Default limits

- file size: 512 MB;
- mesh triangles: 5,000,000;
- absolute coordinate: 1,000,000 mm;
- estimated mesh-analysis memory: 2,048 MB;
- archive entries: 2,048;
- archive expanded size: 1,024 MB;
- compression ratio: 200:1.

Contracts may tighten these limits. They cannot silently loosen CLI/runtime limits.

Use lower limits for automated or shared-file workflows. Do not process confidential designs on untrusted systems merely because Guardian itself is local.
