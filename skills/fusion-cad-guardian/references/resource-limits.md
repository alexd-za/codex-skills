# Mesh resource limits

STL files are untrusted inputs. Guardian performs preflight checks before allocating the full analysis structures.

Default limits:

| Limit | Default |
|---|---:|
| File size | 512 MB |
| Input triangles | 5,000,000 |
| Absolute coordinate magnitude | 1,000,000 mm |
| Estimated Python analysis memory | 2,048 MB |

The memory estimate is deliberately conservative because Python objects consume much more memory than compact STL records.

## CLI overrides

```powershell
py -3 scripts/guardian.py audit part.stl `
  --max-file-size-mb 256 `
  --max-input-triangles 2000000 `
  --max-coordinate-abs-mm 10000 `
  --max-estimated-memory-mb 1024
```

## Contract limits

A contract may contain `resource_limits`. Contract values can only tighten the CLI/default limits; they cannot silently loosen them. This prevents a generated contract from disabling safety controls.

Exceeding a resource limit returns exit code `2` and no acceptance result. It is an input-safety failure, not a failed geometric requirement.
