from enum import StrEnum


class RuleMatchStatus(StrEnum):
    EXACT_MATCH = "EXACT_MATCH"
    COVERED_MATCH = "COVERED_MATCH"
    NEW = "NEW"
    MATCH_ERROR = "MATCH_ERROR"


class SdwanRuleAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DROP = "DROP"
