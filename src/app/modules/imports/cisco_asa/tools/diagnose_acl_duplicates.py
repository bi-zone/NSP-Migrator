"""CLI forensic tool for Cisco ASA ACL duplicate and trace anomalies.

Runs the production parse -> normalize pipeline on a local config file and
prints summary counters for common idempotency / binding / duplication signals.
Not wired into FastAPI, DI, or tests — intended for manual investigation of
customer configs and regression debugging (see project architecture audit notes).

Typical invocation::

    python -m app.modules.imports.cisco_asa.tools.diagnose_acl_duplicates path/to/config.cfg

Metrics printed by run correlate with normalizer behavior:

- duplicate_canonical_rule_key — same CanonicalRule.rule_key twice
  (unexpected after DeterministicRuleKeyBuilder :dupN suffixing).
- duplicate_raw_acl_line_same_context — identical raw ACL line + binding
  context (binding_context= from build_rule_metadata); pairs with
  textual_duplicate_rule issues from emit_textual_duplicate_issue.
- rules_missing_binding_context — unbound / inferred bindings from
  ZoneResolver (no access-group match).
- rules_with_unresolved_zone — count of unresolved_zone issues from
  emit_rule_zone_issues.
- rules_generated_more_than_once_from_same_raw_trace — multiple RULE traces
  for one source line span; **expected** when ZoneResolver.resolve_all fans
  out one ACL line across several interface bindings.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from pathlib import Path
from uuid import uuid4

from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter
from app.modules.trace.domain.enums import TraceCanonicalKind


def run(path: Path) -> None:
    """Parse and normalize one config file; print duplicate/binding diagnostics.

    Uses CiscoAsaParserAdapter and CiscoAsaNormalizerAdapter with a
    synthetic source_snapshot_id (trace/DB persistence not required for
    these counters). All output goes to stdout.

    Args:
        path: Path to raw Cisco ASA configuration text.
    """
    raw = path.read_text()
    parser = CiscoAsaParserAdapter()
    normalizer = CiscoAsaNormalizerAdapter()
    parsed = parser.parse(raw)
    outcome = normalizer.normalize(parsed, source_snapshot_id=uuid4())

    rules = outcome.canonical.rules
    issues = outcome.canonical.issues
    traces = outcome.trace.records

    print(f"file={path}")
    print(f"acl_entries={len(parsed.rules)}")
    print(f"canonical_rules={len(rules)}")

    key_counts = Counter(r.rule_key for r in rules)
    dup_rule_keys = {k: c for k, c in key_counts.items() if c > 1}
    print(f"duplicate_canonical_rule_key={len(dup_rule_keys)}")
    for key, count in sorted(dup_rule_keys.items()):
        print(f"  key={key} count={count}")

    raw_counts = Counter(
        (
            r.section or "",
            _extract_binding_context(r.description),
            _normalize_line(_rule_trace_fragment(traces, r.id)),
        )
        for r in rules
    )
    dup_raw = {k: c for k, c in raw_counts.items() if c > 1}
    print(f"duplicate_raw_acl_line_same_context={len(dup_raw)}")
    for (acl, binding, line), count in sorted(dup_raw.items()):
        print(f"  acl={acl} binding={binding} count={count} line={line}")

    missing_binding = [
        r.rule_key
        for r in rules
        if "binding_context=unbound" in (r.description or "")
        or "binding_context=inferred" in (r.description or "")
    ]
    print(f"rules_missing_binding_context={len(missing_binding)}")

    unresolved_zone = [i for i in issues if i.issue_code == "unresolved_zone"]
    print(f"rules_with_unresolved_zone={len(unresolved_zone)}")

    rules_from_same_trace: dict[tuple[int, int], list[str]] = defaultdict(list)
    for rec in traces:
        if rec.canonical_kind != TraceCanonicalKind.RULE:
            continue
        rules_from_same_trace[(rec.source_line_start, rec.source_line_end)].append(
            str(rec.canonical_id)
        )
    generated_more_than_once = {
        span: ids for span, ids in rules_from_same_trace.items() if len(ids) > 1
    }
    print(
        f"rules_generated_more_than_once_from_same_raw_trace={len(generated_more_than_once)}"
    )
    for span, ids in sorted(generated_more_than_once.items()):
        print(f"  span={span[0]}-{span[1]} generated={len(ids)}")


def _normalize_line(line: str) -> str:
    """Whitespace-normalize and lowercase a trace source_fragment for grouping."""
    return " ".join(line.split()).lower()


def _extract_binding_context(description: str | None) -> str:
    """Parse binding_context=... from CanonicalRule.description metadata.

    Description is built by build_rule_metadata in rules/processing.py.
    Returns unknown when the key is absent.
    """
    if not description:
        return "unknown"
    for part in description.split(";"):
        chunk = part.strip()
        if chunk.startswith("binding_context="):
            return chunk.split("=", 1)[1]
    return "unknown"


def _rule_trace_fragment(traces, rule_id) -> str:
    """Return RULE trace source_fragment for one canonical rule id, or empty."""
    for rec in traces:
        if (
            rec.canonical_kind == TraceCanonicalKind.RULE
            and rec.canonical_id == rule_id
        ):
            return rec.source_fragment or ""
    return ""


def main() -> None:
    """CLI entry: config_path positional argument."""
    ap = argparse.ArgumentParser(
        description="Diagnose Cisco ASA ACL canonical duplicate and trace anomalies."
    )
    ap.add_argument("config_path", type=Path, help="Path to ASA config file")
    args = ap.parse_args()
    run(args.config_path)


if __name__ == "__main__":
    main()