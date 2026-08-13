"""Coarse smoke regression on large real-world config_two_2.cfg."""

from pathlib import Path
from uuid import uuid4

import pytest

from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter

SAMPLE = Path(__file__).resolve().parents[3] / "docs" / "samples" / "config_two_2.cfg"


@pytest.mark.skip
def test_config_two_2_smoke_parse_and_normalize():
    """Large fixture smoke: parser and normalizer should stay stable on volume."""
    raw = SAMPLE.read_text()
    parsed = CiscoAsaParserAdapter().parse(raw)
    outcome = CiscoAsaNormalizerAdapter().normalize(
        parsed, source_snapshot_id=uuid4()
    )
    cmd = outcome.canonical

    assert len(parsed.rules) >= 100
    assert len(cmd.rules) == len(parsed.rules)
    assert len(cmd.objects) >= 50
    assert len(outcome.trace.records) >= len(cmd.rules)
