# JSON Schemas

Guardian v2.1 publishes JSON Schema Draft 2020-12 documents in `schemas/`:

- `contract.schema.json`
- `evidence.schema.json`
- `export-record.schema.json`
- `capability-profile.schema.json`
- `audit-report.schema.json`

Generated contracts, evidence ledgers, capability profiles, and audit reports include a `$schema` URI where applicable.

The dependency-free CLI performs its own strict validation:

```powershell
py -3 scripts/guardian.py validate contract contract.json
py -3 scripts/guardian.py validate evidence evidence.json
py -3 scripts/guardian.py validate capabilities capabilities.json
py -3 scripts/guardian.py validate audit-report reports/part.json
```

The published schemas are for editor completion, external validation, CI, interoperability, and versioned documentation. Runtime validation does not require the third-party `jsonschema` package.
