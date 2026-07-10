"""Compatibility facade for contract validation."""

from .contracts_validation_base import *
from .contracts_validation_contract import validate_contract

__all__ = ["validate_contract"]
