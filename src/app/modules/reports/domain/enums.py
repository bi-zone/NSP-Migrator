from enum import StrEnum


class ReportRuleAction(StrEnum):
    """Action saved with a migrated policy snapshot."""

    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DROP = "DROP"


class ReportRuleMigrationResult(StrEnum):
    """Historical outcome recorded for one report rule."""

    PUSHED = "PUSHED"
    FAILED = "FAILED"

    # Reserved for subsequent producers that include non-push execute outcomes.
    MATCHED = "MATCHED"
    COVERED = "COVERED"
    ERROR = "ERROR"
