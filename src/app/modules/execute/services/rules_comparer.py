from collections import defaultdict
from dataclasses import dataclass
from typing import TypeAlias

from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.domain.value_objects import (
    PlannedRuleDraft,
    RuleBody,
    RuleCompareResult,
    SdwanPolicyCatalog,
    SdwanRule,
)
from app.modules.execute.services.rule_values_resolver import (
    NormalizedRuleValues,
    RuleValueNormalizationError,
    RuleValuesResolver,
)

RuleSignature: TypeAlias = str
RulesIndex: TypeAlias = dict[RuleSignature, list["_ResolvedSdwanRule"]]


@dataclass(frozen=True, slots=True)
class _ResolvedSdwanRule:
    rule: SdwanRule
    values: NormalizedRuleValues


class RulesComparer:
    """Compares planned rules with existing SD-WAN rules by normalized values.

    Existing SD-WAN rules are normalized once during initialization and indexed
    by exact signature. Broken existing rules are skipped because they should not
    block preparation of the execute plan. Broken planned rules are returned as
    MATCH_ERROR because they cannot be safely pushed or compared.
    """

    def __init__(self, *, catalog: SdwanPolicyCatalog) -> None:
        self._resolver = RuleValuesResolver(
            zones=catalog.zones,
            services=catalog.services,
            address_objects=catalog.address_objects,
        )

        self._resolved_sdwan_rules: list[_ResolvedSdwanRule] = []
        self._rules_index: RulesIndex = defaultdict(list)

        for rule in catalog.rules:
            try:
                resolved = _ResolvedSdwanRule(
                    rule=rule,
                    values=self._resolver.normalize_rule(rule),
                )
            except RuleValueNormalizationError:
                continue

            self._resolved_sdwan_rules.append(resolved)
            self._rules_index[resolved.values.exact_signature()].append(resolved)

    def compare_rule(self, rule: RuleBody | PlannedRuleDraft) -> RuleCompareResult:
        """Compare one planned rule against loaded SD-WAN policy catalog."""
        try:
            planned_values = self._resolver.normalize_rule(rule)
        except RuleValueNormalizationError as exc:
            return RuleCompareResult(
                match_status=RuleMatchStatus.MATCH_ERROR,
                matched_sdwan_rule_id=None,
                match_info=f"Error through rules matching: {exc}",
            )

        exact_candidates: list[_ResolvedSdwanRule] = self._rules_index.get(
            planned_values.exact_signature(),
            [],
        )

        if exact_candidates:
            matched_rule_ids = [candidate.rule.id for candidate in exact_candidates]
            return RuleCompareResult(
                match_status=RuleMatchStatus.EXACT_MATCH,
                matched_sdwan_rule_id=matched_rule_ids[0],
                match_info=(
                    f"Found exact match sdwan rule "
                    f"{matched_rule_ids[0]} for planned rule"
                ),
            )

        for existing_rule in self._resolved_sdwan_rules:
            if existing_rule.values.covers(planned_values):
                return RuleCompareResult(
                    match_status=RuleMatchStatus.COVERED_MATCH,
                    matched_sdwan_rule_id=existing_rule.rule.id,
                    match_info=(
                        f"Found cover sdwan rule "
                        f"{existing_rule.rule.id} for planned rule"
                    ),
                )

        return RuleCompareResult(
            match_status=RuleMatchStatus.NEW,
            matched_sdwan_rule_id=None,
            match_info="Clearly new rule for migration",
        )
