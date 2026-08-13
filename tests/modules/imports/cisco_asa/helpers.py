from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4

from app.modules.canonical.domain.enums import OperandRole
from app.modules.imports.cisco_asa.adapters.normalizer import (
    CiscoAsaNormalizerAdapter,
    NormalizeOutcome,
)
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter
from app.modules.imports.cisco_asa.domain.parsed_config import ParsedConfig
from app.modules.trace.domain.enums import TraceCanonicalKind
from app.modules.trace.domain.record import TraceRawToCanonicalRecord

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "fixtures" / "cisco_asa"

TC_FIXTURES: dict[str, str] = {
    "TC_01": "TC_01_acl_iface_in.cfg",
    "TC_02": "TC_02_acl_object_network.cfg",
    "TC_03": "TC_03_acl_object_group_network.cfg",
    "TC_04": "TC_04_acl_object_group_service.cfg",
    "TC_05": "TC_05_acl_no_binding.cfg",
    "TC_06": "TC_06_acl_global.cfg",
    "TC_07": "TC_07_acl_unknown_iface.cfg",
    "TC_08": "TC_08_acl_multi_iface.cfg",
    "TC_09": "TC_09_object_reuse.cfg",
    "TC_10": "TC_10_duplicate_rules.cfg",
    "TC_11": "TC_11_unsupported_group_line.cfg",
    "TC_12": "TC_12_ambiguous_zones.cfg",
    "TC_13": "TC_13_lineage_rules.cfg",
    "TC_14": "TC_14_roundtrip_metadata.cfg",
    "TC_15": "TC_15_icmp_group.cfg",
    "TC_16": "TC_16_nested_group.cfg",
    "TC_17": "TC_17_objects_only.cfg",
    "TC_18": "TC_18_object_subnet.cfg",
    "TC_19": "TC_19_object_service.cfg",
    "TC_20": "TC_20_acl_inline_host.cfg",
    "TC_21": "TC_21_acl_name_zone_inference.cfg",
    "TC_22": "TC_22_acl_inactive.cfg",
    "TC_23": "TC_23_acl_any4.cfg",
}


def fixture_path(tc_id: str) -> Path:
    name = TC_FIXTURES.get(tc_id)
    if name is None:
        raise KeyError(f"Unknown tc_id: {tc_id}")
    path = FIXTURES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(path)
    return path


def load_cfg(tc_id: str) -> str:
    return fixture_path(tc_id).read_text()


def parse_cfg(tc_id: str) -> ParsedConfig:
    return CiscoAsaParserAdapter().parse(load_cfg(tc_id))


def normalize_cfg(
    tc_id: str, *, source_snapshot_id: UUID | None = None
) -> NormalizeOutcome:
    parsed = parse_cfg(tc_id)
    return CiscoAsaNormalizerAdapter().normalize(
        parsed, source_snapshot_id=source_snapshot_id or uuid4()
    )


def objects_by_key(outcome: NormalizeOutcome) -> dict[str, object]:
    return {o.object_key: o for o in outcome.canonical.objects}


def issue_codes(outcome: NormalizeOutcome) -> set[str]:
    return {i.issue_code for i in outcome.canonical.issues}


def trace_for_entity(
    records: list[TraceRawToCanonicalRecord],
    *,
    canonical_kind: TraceCanonicalKind,
    canonical_id: UUID,
) -> list[TraceRawToCanonicalRecord]:
    return [
        r
        for r in records
        if r.canonical_kind == canonical_kind and r.canonical_id == canonical_id
    ]


def traces_on_line(
    records: list[TraceRawToCanonicalRecord], line_no: int
) -> list[TraceRawToCanonicalRecord]:
    return [r for r in records if r.source_line_start <= line_no <= r.source_line_end]


def assert_issue(
    outcome: NormalizeOutcome,
    code: str,
    *,
    entity_key_substr: str | None = None,
) -> None:
    matches = [i for i in outcome.canonical.issues if i.issue_code == code]
    if entity_key_substr is not None:
        matches = [i for i in matches if entity_key_substr in i.entity_key]  # type: ignore
    assert matches, f"Expected issue {code!r}, got {issue_codes(outcome)}"


def assert_no_issue(outcome: NormalizeOutcome, code: str) -> None:
    assert code not in issue_codes(outcome), f"Unexpected issue {code!r}"


def assert_trace_line(
    records: list[TraceRawToCanonicalRecord],
    line_no: int,
    kind: TraceCanonicalKind,
    *,
    role: str | None = None,
) -> None:
    hits = [
        r
        for r in traces_on_line(records, line_no)
        if r.canonical_kind == kind and (role is None or r.canonical_role == role)
    ]
    assert hits, (
        f"No trace kind={kind!r} role={role!r} on line {line_no}; "
        f"lines present: {sorted({r.source_line_start for r in records})}"
    )


def assert_rule_has_trace(outcome: NormalizeOutcome, rule_id: UUID) -> None:
    hits = trace_for_entity(
        outcome.trace.records,
        canonical_kind=TraceCanonicalKind.RULE,
        canonical_id=rule_id,
    )
    assert hits, f"Rule {rule_id} has no RULE trace"


def operand_object_keys(outcome: NormalizeOutcome, rule_id: UUID) -> dict[str, str]:
    by_id = {o.id: o.object_key for o in outcome.canonical.objects}
    result: dict[str, str] = {}
    for op in outcome.canonical.operands:
        if op.rule_id != rule_id:
            continue
        if op.target_object_id and op.operand_role.value in {
            OperandRole.SRC_OBJECT.value,
            OperandRole.DST_OBJECT.value,
            OperandRole.SERVICE.value,
        }:
            result[op.operand_role.value] = by_id[op.target_object_id]
    return result


def line_number_for_substring(cfg: str, substring: str) -> int:
    for i, line in enumerate(cfg.splitlines(), start=1):
        if substring in line and not line.lstrip().startswith("#"):
            return i
    raise ValueError(f"Substring not found in cfg: {substring!r}")
