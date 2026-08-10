from __future__ import annotations

from uuid import UUID, uuid4

from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotCommand,
)
from app.modules.canonical.domain import CanonicalObject, ObjectFamily, ObjectKind
from app.modules.imports.cisco_asa.adapters.normalizer.addresses import (
    _AddressNormalizationMixin,
)
from app.modules.imports.cisco_asa.adapters.normalizer.rules import (
    _RuleNormalizationMixin,
)
from app.modules.imports.cisco_asa.adapters.normalizer.services import (
    _ServiceNormalizationMixin,
)
from app.modules.imports.cisco_asa.adapters.normalizer.state import _NormalizerState
from app.modules.imports.cisco_asa.domain.parsed_config import ParsedConfig
from app.modules.imports.cisco_asa.ports.normalizer import NormalizeOutcome
from app.modules.trace.application.dto import SaveTraceRecordsCommand


class CiscoAsaNormalizerAdapter(
    _AddressNormalizationMixin,
    _ServiceNormalizationMixin,
    _RuleNormalizationMixin,
):
    """Adapt external/parsing behavior through CiscoAsaNormalizerAdapter implementation."""

    def __init__(
        self,
        *,
        normalizer_code: str = "cisco_asa",
        normalizer_version: str = "0.2",
    ) -> None:
        """Initialize CiscoAsaNormalizerAdapter dependencies and runtime options.

        Args:
            normalizer_code: Code persisted into canonical/trace metadata to
                identify the normalizer implementation.
            normalizer_version: Version marker persisted with output artifacts
                for traceability across normalization revisions.
        """
        self._code = normalizer_code
        self._version = normalizer_version

    def normalizer_identity(self) -> tuple[str, str]:
        """Return normalizer code and version.

        Returns:
            A stable (code, version) pair used in canonical snapshot metadata
            and trace records.
        """
        return self._code, self._version

    def normalize(
        self,
        parsed: ParsedConfig,
        *,
        source_snapshot_id: UUID,
    ) -> NormalizeOutcome:
        """Transform parsed config into canonical and trace commands.

        Args:
            parsed: Parsed Cisco ASA configuration model.
            source_snapshot_id: Source snapshot identifier.

        Returns:
            Canonical snapshot command and trace command populated from parsed
            ASA entities and ready for persistence by downstream use cases.
        """
        state = _NormalizerState(
            canonical_snapshot_id=uuid4(),
            source_snapshot_id=source_snapshot_id,
            normalizer_code=self._code,
            normalizer_version=self._version,
        )

        self._register_sentinel_objects(state)
        self._materialize_address_objects(parsed, state)
        self._materialize_address_group_members(parsed, state)
        self._materialize_service_objects(parsed, state)
        self._materialize_service_group_members(parsed, state)
        self._materialize_protocol_group_members(parsed, state)
        self._materialize_rules(parsed, state)

        canonical_cmd = SaveCanonicalSnapshotCommand(
            source_snapshot_id=source_snapshot_id,
            normalizer_code=self._code,
            normalizer_version=self._version,
            zones=list(state.zones_by_key.values()),
            objects=list(state.objects_by_id.values()),
            object_members=state.object_members,
            rules=state.rules,
            operands=state.operands,
            issues=state.issues,
        )
        trace_cmd = SaveTraceRecordsCommand(records=state.trace_records)
        return NormalizeOutcome(canonical=canonical_cmd, trace=trace_cmd)

    @staticmethod
    def _register_sentinel_objects(state: _NormalizerState) -> None:
        """Register baseline entities required by downstream normalization steps.

        Args:
            state: Mutable normalization state accumulator shared across helper methods.

        Returns:
            None. The routine mutates provided state in place.
        """
        state.register(
            CanonicalObject.create(
                canonical_snapshot_id=state.canonical_snapshot_id,
                object_key="addr:any",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.ANY_ADDR,
                name="any",
            )
        )
        state.register(
            CanonicalObject.create(
                canonical_snapshot_id=state.canonical_snapshot_id,
                object_key="service:any",
                object_family=ObjectFamily.SERVICE,
                object_kind=ObjectKind.ANY_SERVICE,
                name="any",
            )
        )
