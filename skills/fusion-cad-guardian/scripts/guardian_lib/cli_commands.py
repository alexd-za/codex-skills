"""Compatibility facade for Guardian CLI commands."""

from .cli_project_commands import (
    SCRIPT_DIR, _cmd_capabilities_init, _cmd_capabilities_set, _cmd_evidence_hash,
    _cmd_evidence_init, _cmd_init, _cmd_part_add, _cmd_plan, _cmd_project,
    _parse_part, _resource_limits, _write_outputs,
)
from .cli_analysis_commands import (
    _cmd_audit, _cmd_batch, _cmd_compare, _cmd_inspect_3mf,
    _cmd_slicer_audit, _cmd_validate,
)
from .cli_release_commands import (
    _cmd_bundle, _cmd_bundle_verify, _cmd_doctor, _cmd_gate,
    _cmd_migrate, _cmd_self_test,
)

__all__ = [name for name in globals() if name.startswith("_cmd_") or name in {
    "SCRIPT_DIR", "_parse_part", "_resource_limits", "_write_outputs",
}]
