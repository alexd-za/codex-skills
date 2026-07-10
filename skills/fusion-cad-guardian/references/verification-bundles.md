# Verification bundles

A Guardian bundle is a ZIP evidence package containing `manifest.json` and selected project files. Each manifest entry records a path, byte size, and SHA-256.

By default, project bundles include contracts, evidence, capabilities, plans, task notes, reports, and snapshots. `--include-exports` also includes `exports/` and `gcode/`; use it only when file size and confidentiality are acceptable.

## Integrity properties

- member paths are normalized and traversal is rejected;
- duplicate and encrypted members are rejected;
- creation and verification are streamed;
- entry count, archive size, expanded size, and compression ratio are limited;
- every declared file is hashed and sized;
- missing, changed, or unexpected members fail verification;
- ZIP metadata timestamps are normalized; `SOURCE_DATE_EPOCH` can make the manifest timestamp deterministic.

A verified bundle proves only that its files match its manifest. It does not prove the truth of evidence recorded inside those files.

Store the bundle SHA-256 separately when transmitting or archiving it.
