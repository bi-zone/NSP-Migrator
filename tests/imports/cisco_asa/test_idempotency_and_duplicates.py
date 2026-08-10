"""Idempotency and duplicate-handling tests for Cisco ASA import pipeline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID, uuid4

from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotResult,
)
from app.modules.canonical.domain.enums import SnapshotStatus
from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingCommand,
    RunCiscoMappingUseCase,
)
from app.modules.trace.domain.enums import TraceCanonicalKind

SHARED_ACL_MULTI_BINDING_CFG = """
access-list SHARED_ACL extended permit ip any any
access-group SHARED_ACL in interface outside
access-group SHARED_ACL in interface dmz
interface outside
 nameif outside
interface dmz
 nameif dmz
"""


def _normalize(raw_cfg: str):
    parsed = CiscoAsaParserAdapter().parse(raw_cfg)
    return CiscoAsaNormalizerAdapter().normalize(parsed, source_snapshot_id=uuid4())


def _rule_keys(outcome) -> list[str]:  # noqa: ANN001
    return [rule.rule_key for rule in outcome.canonical.rules]


def _issue_codes(outcome) -> set[str]:  # noqa: ANN001
    return {issue.issue_code for issue in outcome.canonical.issues}


def _rule_traces(outcome, *, rule_id: UUID):  # noqa: ANN001
    return [
        record
        for record in outcome.trace.records
        if record.canonical_kind == TraceCanonicalKind.RULE
        and record.canonical_id == rule_id
    ]


# ---------------------------------------------------------------------------
# Normalizer behavior: keys, duplicate marking, and trace fidelity
# ---------------------------------------------------------------------------
def test_multi_interface_binding_creates_distinct_rule_keys_per_context():
    outcome = _normalize(SHARED_ACL_MULTI_BINDING_CFG)

    assert _rule_keys(outcome) == ["SHARED_ACL:1", "SHARED_ACL:1:dup1"]
    descriptions = [rule.description or "" for rule in outcome.canonical.rules]
    assert any("binding_context=interface:outside:in" in desc for desc in descriptions)
    assert any("binding_context=interface:dmz:in" in desc for desc in descriptions)


def test_textual_duplicate_is_marked_but_rules_are_preserved():
    raw_cfg = """
access-list ACL_OUT extended permit tcp any host 10.0.0.10 eq 443
access-list ACL_OUT extended permit tcp any host 10.0.0.10 eq 443
access-group ACL_OUT in interface outside
interface outside
 nameif outside
"""
    outcome = _normalize(raw_cfg)

    assert len(outcome.canonical.rules) == 2
    assert "textual_duplicate_rule" in _issue_codes(outcome)


def test_same_text_in_different_acls_is_not_marked_as_duplicate():
    raw_cfg = """
access-list ACL_A extended permit ip any any
access-list ACL_B extended permit ip any any
"""
    outcome = _normalize(raw_cfg)

    assert "textual_duplicate_rule" not in _issue_codes(outcome)


def test_rule_trace_keeps_exact_raw_acl_line_text():
    raw_acl_line = "access-list ACL_OUT extended deny tcp any any eq 22"
    raw_cfg = f"""
{raw_acl_line}
access-group ACL_OUT in interface outside
interface outside
 nameif outside
"""
    outcome = _normalize(raw_cfg)
    traces = _rule_traces(outcome, rule_id=outcome.canonical.rules[0].id)

    assert traces
    assert traces[0].source_fragment == raw_acl_line


def test_rule_key_suffix_is_stable_for_repeated_normalization():
    first = _normalize(SHARED_ACL_MULTI_BINDING_CFG)
    second = _normalize(SHARED_ACL_MULTI_BINDING_CFG)

    assert _rule_keys(first) == ["SHARED_ACL:1", "SHARED_ACL:1:dup1"]
    assert _rule_keys(second) == ["SHARED_ACL:1", "SHARED_ACL:1:dup1"]


# ---------------------------------------------------------------------------
# Use-case behavior: idempotent mapping path
# ---------------------------------------------------------------------------
@dataclass
class _FakeSnapshot:
    id: UUID
    status: SnapshotStatus


class _FakeSnapshotsRepo:
    def __init__(self, existing: _FakeSnapshot | None):
        self.existing = existing
        self.queries = 0

    async def get_by_source_and_normalizer(self, **_: object):
        self.queries += 1
        return self.existing


class _FakeCanonicalUow:
    def __init__(self, snapshots_repo: _FakeSnapshotsRepo):
        self.session = None
        self.snapshots = snapshots_repo

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def commit(self):
        return None

    def __call__(self, reuse_session: bool = False):  # noqa: ARG002
        return self


class _FakeSaveCanonicalSnapshotUseCase:
    def __init__(self, snapshots_repo: _FakeSnapshotsRepo, result_id: UUID):
        self.uow = _FakeCanonicalUow(snapshots_repo)
        self.calls = 0
        self.result_id = result_id

    async def execute(self, command):  # noqa: ANN001
        self.calls += 1
        existing = self.uow.snapshots.existing
        if existing is not None and existing.status == SnapshotStatus.SUCCESS:
            return SaveCanonicalSnapshotResult(
                canonical_snapshot_id=existing.id,
                created=False,
            )
        return SaveCanonicalSnapshotResult(
            canonical_snapshot_id=self.result_id,
            created=True,
        )


class _FakeSaveTraceRecordsUseCase:
    def __init__(self):
        self.calls = 0

    async def execute(self, command):  # noqa: ANN001
        self.calls += 1
        return SimpleNamespace(written=len(command.records))


class _FakeImportsArtifactsRepo:
    def __init__(self, raw_text: str):
        self._raw_text = raw_text
        self.calls = 0

    async def get_by_snapshot_id(self, _: UUID):
        self.calls += 1
        return SimpleNamespace(raw_text=self._raw_text)


class _FakeImportsUow:
    def __init__(self, raw_text: str):
        self.session = None
        self.artifacts = _FakeImportsArtifactsRepo(raw_text)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):  # noqa: ANN001
        return False

    async def commit(self):
        return None

    def __call__(self, reuse_session: bool = False):  # noqa: ARG002
        return self


def test_mapping_use_case_reuses_existing_snapshot_without_trace_rewrite():
    source_snapshot_id = uuid4()
    existing_snapshot_id = uuid4()
    fake_snapshots = _FakeSnapshotsRepo(
        _FakeSnapshot(id=existing_snapshot_id, status=SnapshotStatus.SUCCESS)
    )
    save_canonical = _FakeSaveCanonicalSnapshotUseCase(
        fake_snapshots,
        result_id=uuid4(),
    )
    save_trace = _FakeSaveTraceRecordsUseCase()
    imports_uow = _FakeImportsUow("access-list ACL_A extended permit ip any any")
    use_case = RunCiscoMappingUseCase(
        uow=imports_uow,
        parser=CiscoAsaParserAdapter(),
        normalizer=CiscoAsaNormalizerAdapter(),
        save_canonical_snapshot=save_canonical,
        save_trace_records=save_trace,
    )

    result = asyncio.run(
        use_case.execute(RunCiscoMappingCommand(source_snapshot_id=source_snapshot_id))
    )

    assert result.canonical_snapshot_id == existing_snapshot_id
    assert result.trace_records_written == 0
    assert save_canonical.calls == 1
    assert save_trace.calls == 0
    assert imports_uow.artifacts.calls == 1

