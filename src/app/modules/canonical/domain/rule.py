"""Canonical firewall rule and operand entities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.modules.canonical.domain.enums import OperandRole


@dataclass(slots=True)
class CanonicalRule:
    """Normalized ACL rule within a snapshot."""

    id: UUID
    canonical_snapshot_id: UUID
    rule_key: str
    name: str
    action: str
    enabled: bool
    priority: int
    section: str | None
    description: str | None

    @classmethod
    def create(
        cls,
        *,
        canonical_snapshot_id: UUID,
        rule_key: str,
        name: str,
        action: str,
        enabled: bool,
        priority: int,
        section: str | None = None,
        description: str | None = None,
    ) -> CanonicalRule:
        return cls(
            id=uuid4(),
            canonical_snapshot_id=canonical_snapshot_id,
            rule_key=rule_key,
            name=name,
            action=action,
            enabled=enabled,
            priority=priority,
            section=section,
            description=description,
        )


@dataclass(slots=True)
class CanonicalRuleOperand:
    id: UUID
    rule_id: UUID
    operand_role: OperandRole
    target_zone_id: UUID | None
    target_object_id: UUID | None
    position: int

    @classmethod
    def create(
        cls,
        *,
        rule_id: UUID,
        operand_role: OperandRole,
        target_zone_id: UUID | None = None,
        target_object_id: UUID | None = None,
        position: int = 0,
    ) -> CanonicalRuleOperand:
        return cls(
            id=uuid4(),
            rule_id=rule_id,
            operand_role=operand_role,
            target_zone_id=target_zone_id,
            target_object_id=target_object_id,
            position=position,
        )
