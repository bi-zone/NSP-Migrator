"""Extension cases with spec-vs-baseline xfail markers."""

from __future__ import annotations

import pytest

from app.core.errors import DomainValidationError

from tests.imports.cisco_asa.helpers import normalize_cfg, parse_cfg


def test_tc_17_baseline_parser_hard_fail():
    with pytest.raises(DomainValidationError, match="No ACL rules found"):
        parse_cfg("TC_17")


@pytest.mark.xfail(
    reason="TC-17 spec: partial snapshot + no_acl_rules issue without hard-fail"
)
def test_tc_17_partial_import_spec():
    outcome = normalize_cfg("TC_17")
    assert outcome.canonical.rules == []
    assert any(i.issue_code == "no_acl_rules" for i in outcome.canonical.issues)
