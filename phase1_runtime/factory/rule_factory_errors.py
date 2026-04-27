from __future__ import annotations


class RuleFactoryError(ValueError):
    """Raised when a factory lifecycle transition violates publish gates."""
