import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import TypeAlias

from app.modules.execute.domain.enums import RuleMatchStatus
from app.modules.execute.domain.value_objects import (
    ExcludedExistingRule,
    PlannedRuleDraft,
    RuleBody,
    RuleCompareResult,
    SdwanPolicyCatalog,
    SdwanRule,
)
from app.modules.execute.services.rule_values_resolver import (
    ResolvedRuleValues,
    RuleValueNormalizationError,
    RuleValuesResolver,
)

logger = logging.getLogger(__name__)

RuleSignature: TypeAlias = str
RulesIndex: TypeAlias = dict[RuleSignature, list["_ResolvedSdwanRule"]]


@dataclass(frozen=True, slots=True)
class _ResolvedSdwanRule:
    rule: SdwanRule
    values: ResolvedRuleValues


class RulesComparer:
    """Compares planned rules with existing SD-WAN rules by normalized values.

    Existing SD-WAN rules are normalized once during initialization and indexed
    by exact signature. Broken existing rules are excluded and recorded because
    they should not block preparation of the execute plan. Broken planned rules
    are returned as MATCH_ERROR because they cannot be safely pushed or compared.
    """

    def __init__(self, *, catalog: SdwanPolicyCatalog) -> None:
        self._resolver = RuleValuesResolver(
            zones=catalog.zones,
            services=catalog.services,
            address_objects=catalog.address_objects,
        )

        self._resolved_sdwan_rules: list[_ResolvedSdwanRule] = []
        self._rules_index: RulesIndex = defaultdict(list)
        self._excluded_existing_rules: list[ExcludedExistingRule] = []

        for rule in catalog.rules:
            try:
                resolved = _ResolvedSdwanRule(
                    rule=rule,
                    values=self._resolver.resolve_rule(rule),
                )
            except RuleValueNormalizationError as exc:
                self._excluded_existing_rules.append(
                    ExcludedExistingRule(
                        sdwan_rule_id=rule.id,
                        reason=str(exc),
                    )
                )
                continue

            self._resolved_sdwan_rules.append(resolved)
            self._rules_index[resolved.values.exact_signature()].append(resolved)

    @property
    def excluded_existing_rules(self) -> tuple[ExcludedExistingRule, ...]:
        """Return SD-WAN policies omitted from comparison and their reasons."""
        return tuple(self._excluded_existing_rules)

    def compare_rule(self, rule: RuleBody | PlannedRuleDraft) -> RuleCompareResult:
        """Compare one planned rule against loaded SD-WAN policy catalog."""
        try:
            planned_values = self._resolver.resolve_rule(rule)
        except RuleValueNormalizationError as exc:
            _err_str = f"Error through rules matching: {exc}"
            logger.error(_err_str)
            return RuleCompareResult(
                match_status=RuleMatchStatus.MATCH_ERROR,
                matched_sdwan_rule_id=None,
                match_info=_err_str,
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
            coverage = self._resolver.analyze_coverage(
                existing=existing_rule.values,
                planned=planned_values,
            )
            if coverage.is_covered:
                return RuleCompareResult(
                    match_status=RuleMatchStatus.COVERED_MATCH,
                    matched_sdwan_rule_id=existing_rule.rule.id,
                    match_info=(
                        f"Found cover sdwan rule "
                        f"{existing_rule.rule.id} for planned rule"
                    ),
                    coverage_details=coverage.details,
                )

        return RuleCompareResult(
            match_status=RuleMatchStatus.NEW,
            matched_sdwan_rule_id=None,
            match_info="Clearly new rule for migration",
        )
