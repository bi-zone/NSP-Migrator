"""Canonical integration-test fixtures backed by the migrated PostgreSQL DB.

The shared module fixtures own database creation, Alembic migration, and cleanup.
This file adds only canonical-specific wiring and a representative policy graph.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.session_factory import SQLAlchemySessionFactory
from app.modules.canonical.adapters.db.uow import CanonicalUoW
from app.modules.canonical.application.use_cases.save_canonical_snapshot import (
    SaveCanonicalSnapshotCommand,
    SaveCanonicalSnapshotUseCase,
)
from app.modules.canonical.domain import (
    CanonicalIssue,
    CanonicalObject,
    CanonicalObjectMember,
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalZone,
    ObjectFamily,
    ObjectKind,
    OperandRole,
)


@dataclass(frozen=True, slots=True)
class CanonicalScenario:
    """Persisted canonical graph plus stable entity handles used by assertions."""

    source_snapshot_id: UUID
    snapshot_id: UUID
    zones: dict[str, CanonicalZone]
    objects: dict[str, CanonicalObject]
    rules: dict[str, CanonicalRule]
    members: list[CanonicalObjectMember]
    operands: list[CanonicalRuleOperand]
    issues: list[CanonicalIssue]


@pytest.fixture
def canonical_uow_factory(
    session_factory: SQLAlchemySessionFactory,
) -> Callable[[], CanonicalUoW]:
    """Return fresh real canonical UoWs so each use case owns its transaction."""

    def _factory() -> CanonicalUoW:
        return CanonicalUoW(session_factory)

    return _factory


async def _seed_source_snapshot(session: AsyncSession, *, label: str) -> UUID:
    """Persist the imports parent rows required by canonical_snapshot's FK."""
    token = uuid4().hex[:10]
    vendor_code = f"canonical-test-{token}"
    source_id = uuid4()
    source_snapshot_id = uuid4()
    await session.execute(
        text(
            """
            INSERT INTO import_vendor (code, display_name, active)
            VALUES (:vendor_code, :display_name, true)
            """
        ),
        {"vendor_code": vendor_code, "display_name": f"Canonical {label}"},
    )
    await session.execute(
        text(
            """
            INSERT INTO import_source
                (id, vendor_code, name, description, active)
            VALUES
                (:source_id, :vendor_code, :name, NULL, true)
            """
        ),
        {
            "source_id": source_id,
            "vendor_code": vendor_code,
            "name": f"source-{label}-{token}",
        },
    )
    await session.execute(
        text(
            """
            INSERT INTO source_snapshot
                (id, source_id, artifact_hash, source_format, is_latest)
            VALUES
                (:snapshot_id, :source_id, :artifact_hash, 'cisco_asa', true)
            """
        ),
        {
            "snapshot_id": source_snapshot_id,
            "source_id": source_id,
            "artifact_hash": token.ljust(64, "0"),
        },
    )
    await session.commit()
    return source_snapshot_id


@pytest.fixture
def canonical_scenario_factory(
    db_session: AsyncSession,
    canonical_uow_factory: Callable[[], CanonicalUoW],
) -> Callable[..., object]:
    """Create a rich canonical graph through the real save use case."""

    async def _create(*, label: str = "primary") -> CanonicalScenario:
        source_snapshot_id = await _seed_source_snapshot(db_session, label=label)
        placeholder_snapshot_id = uuid4()

        zones = {
            "outside": CanonicalZone.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                zone_key=f"outside-{label}",
                name=f"Perimeter {label}",
                direction_hint="in",
            ),
            "inside": CanonicalZone.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                zone_key=f"inside-{label}",
                name=f"Trusted {label}",
                direction_hint="out",
            ),
            "dmz": CanonicalZone.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                zone_key=f"dmz-{label}",
                name=f"DMZ {label}",
            ),
            "unused": CanonicalZone.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                zone_key=f"unused-{label}",
                name=f"Unused {label}",
            ),
        }
        objects = {
            "payroll_host": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"payroll-host-{label}",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.HOST,
                name=f"Payroll Host {label}",
                ip_version=4,
                cidr="10.20.30.40/32",
            ),
            "inner_group": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"inner-finance-{label}",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.ADDR_GROUP,
                name=f"Inner Finance {label}",
            ),
            "outer_group": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"finance-bundle-{label}",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.ADDR_GROUP,
                name=f"Finance Bundle {label}",
            ),
            "fqdn": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"blocked-fqdn-{label}",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.FQDN,
                name=f"Blocked Portal {label}",
                fqdn=f"blocked-{label}.example",
            ),
            "admin_host": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"admin-host-{label}",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.HOST,
                name=f"Admin Host {label}",
                ip_version=4,
                cidr="192.0.2.10/32",
            ),
            "http": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"tcp-443-{label}",
                object_family=ObjectFamily.SERVICE,
                object_kind=ObjectKind.TCP,
                name=f"HTTPS {label}",
                protocol="tcp",
                port_from=443,
                port_to=443,
            ),
            "dns": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"udp-53-{label}",
                object_family=ObjectFamily.SERVICE,
                object_kind=ObjectKind.UDP,
                name=f"DNS {label}",
                protocol="udp",
                port_from=53,
                port_to=53,
            ),
            "unused": CanonicalObject.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                object_key=f"unused-object-{label}",
                object_family=ObjectFamily.ADDR,
                object_kind=ObjectKind.SUBNET,
                name=f"Unused Object {label}",
                ip_version=4,
                cidr="198.51.100.0/24",
            ),
        }
        members = [
            CanonicalObjectMember.create(
                parent_object_id=objects["outer_group"].id,
                child_object_id=objects["inner_group"].id,
                position=0,
            ),
            CanonicalObjectMember.create(
                parent_object_id=objects["inner_group"].id,
                child_object_id=objects["payroll_host"].id,
                position=0,
            ),
        ]
        rules = {
            "nested": CanonicalRule.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                rule_key=f"allow-finance-{label}",
                name=f"Allow Nested Payroll {label}",
                action="permit",
                enabled=True,
                priority=30,
                section="outside_in",
                description="processing_status=fw_applicable",
            ),
            "blocked": CanonicalRule.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                rule_key=f"block-portal-{label}",
                name=f"Block Portal {label}",
                action="deny",
                enabled=False,
                priority=10,
                section="dmz_in",
                description="processing_status=skipped_for_now",
            ),
            "admin": CanonicalRule.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                rule_key=f"review-admin-{label}",
                name=f"Review Admin Orchid {label}",
                action="permit",
                enabled=True,
                priority=20,
                section="audit",
                description="rule-text-orchid processing_status=fw_applicable",
            ),
        }
        operands = [
            CanonicalRuleOperand.create(
                rule_id=rules["nested"].id,
                operand_role=OperandRole.SRC_ZONE,
                target_zone_id=zones["outside"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["nested"].id,
                operand_role=OperandRole.DST_ZONE,
                target_zone_id=zones["inside"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["nested"].id,
                operand_role=OperandRole.SRC_OBJECT,
                target_object_id=objects["outer_group"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["nested"].id,
                operand_role=OperandRole.SERVICE,
                target_object_id=objects["http"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["blocked"].id,
                operand_role=OperandRole.SRC_ZONE,
                target_zone_id=zones["dmz"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["blocked"].id,
                operand_role=OperandRole.DST_OBJECT,
                target_object_id=objects["fqdn"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["blocked"].id,
                operand_role=OperandRole.SERVICE,
                target_object_id=objects["dns"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["admin"].id,
                operand_role=OperandRole.SRC_ZONE,
                target_zone_id=zones["inside"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["admin"].id,
                operand_role=OperandRole.DST_OBJECT,
                target_object_id=objects["admin_host"].id,
            ),
            CanonicalRuleOperand.create(
                rule_id=rules["admin"].id,
                operand_role=OperandRole.SERVICE,
                target_object_id=objects["http"].id,
            ),
        ]
        issues = [
            CanonicalIssue.create(
                canonical_snapshot_id=placeholder_snapshot_id,
                entity_type="rule",
                entity_key=rules["blocked"].rule_key,
                issue_code="CANONICAL_TEST_WARNING",
                message=f"Synthetic warning for {label}",
                source_line_start=40,
                source_line_end=41,
            )
        ]

        result = await SaveCanonicalSnapshotUseCase(canonical_uow_factory()).execute(
            SaveCanonicalSnapshotCommand(
                source_snapshot_id=source_snapshot_id,
                normalizer_code="canonical_test",
                normalizer_version=f"1-{label}",
                zones=list(zones.values()),
                objects=list(objects.values()),
                object_members=members,
                rules=list(rules.values()),
                operands=operands,
                issues=issues,
            )
        )
        return CanonicalScenario(
            source_snapshot_id=source_snapshot_id,
            snapshot_id=result.canonical_snapshot_id,
            zones=zones,
            objects=objects,
            rules=rules,
            members=members,
            operands=operands,
            issues=issues,
        )

    return _create
