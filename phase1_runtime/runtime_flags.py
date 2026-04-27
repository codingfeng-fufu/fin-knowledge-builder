from __future__ import annotations


# Global switch for a "no rules" runtime state.
# Keep fixture files and draft/publish machinery intact, but let all runtime
# entrypoints see an empty active rule set so requests fall through to
# exploration/no-rule discovery.
DISABLE_ALL_RUNTIME_RULES = False


def runtime_rules_disabled() -> bool:
    return DISABLE_ALL_RUNTIME_RULES
