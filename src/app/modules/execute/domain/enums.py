from enum import StrEnum


class RuleMatchStatus(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    COVERED_MATCH = "COVERED_MATCH"
    NEW = "NEW"
    MATCH_ERROR = "MATCH_ERROR"


class RulePushStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class ExecutePlanPushStatus(StrEnum):
    PENDING = "PENDING"
    EXECUTED = "EXECUTED"


class CoverageField(StrEnum):
    """Rule field whose planned values are covered by an existing policy."""

    SRC_ADDR_OBJECTS = "SRC_ADDR_OBJECTS"
    DST_ADDR_OBJECTS = "DST_ADDR_OBJECTS"
    SERVICES = "SERVICES"


class SdwanRuleAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DROP = "DROP"
