"""Regression tests for rule-level issue code emission."""

from __future__ import annotations

from uuid import uuid4

from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter


def _issue_codes(raw_cfg: str) -> set[str]:
    parsed = CiscoAsaParserAdapter().parse(raw_cfg)
    outcome = CiscoAsaNormalizerAdapter().normalize(
        parsed,
        source_snapshot_id=uuid4(),
    )
    return {issue.issue_code for issue in outcome.canonical.issues}


def test_emits_protocol_unresolved_for_out_of_range_protocol_number():
    raw_cfg = """
access-list ACL_IN extended permit 999 any any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    assert "protocol_unresolved" in _issue_codes(raw_cfg)


def test_emits_protocol_mapping_missing_for_unknown_protocol_group():
    raw_cfg = """
access-list ACL_IN extended permit object-group MISSING_PROTO any any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    assert "protocol_mapping_missing" in _issue_codes(raw_cfg)


def test_emits_usage_conflict_for_acl_used_by_firewall_and_crypto_map():
    raw_cfg = """
access-list ACL_SHARED extended permit ip any any
access-group ACL_SHARED in interface inside
interface inside
 nameif inside
crypto map OUTSIDE_MAP 10 match address ACL_SHARED
"""
    assert "usage_conflict" in _issue_codes(raw_cfg)


def test_emits_crypto_map_selector_for_acl_used_only_by_crypto_map():
    raw_cfg = """
access-list ACL_CRYPTO extended permit ip any any
crypto map OUTSIDE_MAP 10 match address ACL_CRYPTO
"""
    assert "crypto_map_selector" in _issue_codes(raw_cfg)


def test_emits_unresolved_address_ref_for_missing_named_address_object():
    raw_cfg = """
access-list ACL_IN extended permit ip OBJ_MISSING any
access-group ACL_IN in interface inside
interface inside
 nameif inside
"""
    assert "unresolved_address_ref" in _issue_codes(raw_cfg)
