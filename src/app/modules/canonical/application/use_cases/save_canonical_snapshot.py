"""Internal write use case for persisting canonical snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.infrastructure.db.transactional import async_transactional
from app.modules.canonical.domain import (
    CanonicalIssue,
    CanonicalObject,
    CanonicalObjectMember,
    CanonicalRule,
    CanonicalRuleOperand,
    CanonicalSnapshot,
    CanonicalZone,
    SnapshotStatus,
)
from app.modules.canonical.ports.uow import CanonicalUoWPort


@dataclass(slots=True)
class SaveCanonicalSnapshotCommand:
    """Full canonical graph produced by an imports normalizer."""

    source_snapshot_id: UUID
    normalizer_code: str
    normalizer_version: str
    zones: list[CanonicalZone]
    objects: list[CanonicalObject]
    object_members: list[CanonicalObjectMember]
    rules: list[CanonicalRule]
    operands: list[CanonicalRuleOperand]
    issues: list[CanonicalIssue]


@dataclass(slots=True)
class SaveCanonicalSnapshotResult:
    """Outcome of a save attempt.

    Attributes:
        canonical_snapshot_id: Existing or newly persisted snapshot ID.
        created: False when an existing SUCCESS snapshot was reused (idempotent).
    """

    canonical_snapshot_id: UUID
    created: bool = True


class SaveCanonicalSnapshotUseCase:
    """Persist one canonical snapshot graph with idempotent header semantics.

    Called from imports/cisco_asa mapping flow. Reuses existing SUCCESS
    snapshot for the same (source_snapshot_id, normalizer_code, version) key.
    """

    def __init__(self, uow: CanonicalUoWPort) -> None:
        self.uow = uow

    @async_transactional()
    async def execute(
        self, command: SaveCanonicalSnapshotCommand
    ) -> SaveCanonicalSnapshotResult:
        existing = await self.uow.snapshots.get_by_source_and_normalizer(
            source_snapshot_id=command.source_snapshot_id,
            normalizer_code=command.normalizer_code,
            normalizer_version=command.normalizer_version,
        )
        if existing is not None and existing.status == SnapshotStatus.SUCCESS:
            return SaveCanonicalSnapshotResult(
                canonical_snapshot_id=existing.id,
                created=False,
            )

        snapshot = CanonicalSnapshot.create(
            source_snapshot_id=command.source_snapshot_id,
            normalizer_code=command.normalizer_code,
            normalizer_version=command.normalizer_version,
            status=SnapshotStatus.PENDING,
        )

        # persist snapshot header first so children can reference it as FK
        try:
            await self.uow.snapshots.save(snapshot)
        except IntegrityError:
            # Concurrent save for the same idempotency key: re-read and reuse.
            existing = await self.uow.snapshots.get_by_source_and_normalizer(
                source_snapshot_id=command.source_snapshot_id,
                normalizer_code=command.normalizer_code,
                normalizer_version=command.normalizer_version,
            )
            if existing is not None:
                return SaveCanonicalSnapshotResult(
                    canonical_snapshot_id=existing.id,
                    created=False,
                )
            raise

        # rewrite incoming child entities with the real canonical_snapshot_id
        zones = [
            CanonicalZone(
                id=z.id,
                canonical_snapshot_id=snapshot.id,
                zone_key=z.zone_key,
                name=z.name,
                direction_hint=z.direction_hint,
                description=z.description,
            )
            for z in command.zones
        ]
        objects = [
            CanonicalObject(
                id=o.id,
                canonical_snapshot_id=snapshot.id,
                object_key=o.object_key,
                object_family=o.object_family,
                object_kind=o.object_kind,
                name=o.name,
                ip_version=o.ip_version,
                cidr=o.cidr,
                range_start=o.range_start,
                range_end=o.range_end,
                fqdn=o.fqdn,
                protocol=o.protocol,
                port_from=o.port_from,
                port_to=o.port_to,
                icmp_type=o.icmp_type,
                icmp_code=o.icmp_code,
                description=o.description,
            )
            for o in command.objects
        ]
        rules = [
            CanonicalRule(
                id=r.id,
                canonical_snapshot_id=snapshot.id,
                rule_key=r.rule_key,
                name=r.name,
                action=r.action,
                enabled=r.enabled,
                priority=r.priority,
                section=r.section,
                description=r.description,
            )
            for r in command.rules
        ]
        issues = [
            CanonicalIssue(
                id=i.id,
                canonical_snapshot_id=snapshot.id,
                entity_type=i.entity_type,
                entity_key=i.entity_key,
                issue_code=i.issue_code,
                message=i.message,
                source_line_start=i.source_line_start,
                source_line_end=i.source_line_end,
                created_at=i.created_at,
            )
            for i in command.issues
        ]

        await self.uow.zones.bulk_save(zones)
        await self.uow.objects.bulk_save(objects)
        await self.uow.objects.bulk_save_members(command.object_members)
        await self.uow.rules.bulk_save(rules)
        await self.uow.rules.bulk_save_operands(command.operands)
        await self.uow.snapshots.save_issues(issues)

        await self.uow.snapshots.update_counts(
            snapshot_id=snapshot.id,
            zones_total=len(zones),
            objects_total=len(objects),
            rules_total=len(rules),
            issues_total=len(issues),
        )
        await self.uow.snapshots.update_status(snapshot.id, SnapshotStatus.SUCCESS)

        return SaveCanonicalSnapshotResult(canonical_snapshot_id=snapshot.id)
