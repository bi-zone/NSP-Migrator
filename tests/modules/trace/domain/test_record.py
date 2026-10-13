"""Domain unit tests for TraceRawToCanonicalRecord."""

from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord


def _create(**overrides) -> TraceRawToCanonicalRecord:
    defaults = {
        "source_snapshot_id": uuid4(),
        "canonical_snapshot_id": uuid4(),
        "vendor_code": "cisco_asa",
        "normalizer_code": "cisco_asa",
        "normalizer_version": "1",
        "source_line_start": 1,
        "source_line_end": 1,
        "canonical_kind": TraceCanonicalKind.RULE,
        "canonical_id": uuid4(),
    }
    defaults.update(overrides)
    return TraceRawToCanonicalRecord.create(**defaults)


def test_create_rejects_source_line_start_below_one() -> None:
    with pytest.raises(ValueError, match="source_line_start must be >= 1"):
        _create(source_line_start=0, source_line_end=1)


def test_create_rejects_source_line_end_before_start() -> None:
    with pytest.raises(ValueError, match="source_line_end .* must be >="):
        _create(source_line_start=10, source_line_end=9)


def test_with_canonical_snapshot_id_rebounds_only_snapshot_id() -> None:
    source_snapshot_id = uuid4()
    old_canonical_snapshot_id = uuid4()
    new_canonical_snapshot_id = uuid4()
    record = _create(
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=old_canonical_snapshot_id,
        source_line_start=1,
        source_line_end=1,
        source_fragment="access-list ACL_IN",
        canonical_role="header",
    )

    rebound = record.with_canonical_snapshot_id(new_canonical_snapshot_id)

    assert rebound.canonical_snapshot_id == new_canonical_snapshot_id
    assert rebound.id == record.id
    assert rebound.source_snapshot_id == source_snapshot_id
    assert rebound.source_fragment == record.source_fragment
    assert rebound.canonical_kind == record.canonical_kind
    assert rebound.canonical_id == record.canonical_id
    assert rebound.canonical_role == record.canonical_role
