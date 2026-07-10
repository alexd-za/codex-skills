"""Compatibility facade for evidence evaluation and acceptance."""

from .evidence_provenance import evaluate_evidence, populate_export_hashes, verify_export_provenance
from .evidence_acceptance import gate

__all__ = ["evaluate_evidence", "populate_export_hashes", "verify_export_provenance", "gate"]
