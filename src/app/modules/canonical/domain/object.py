"""Canonical address/service object entities."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from app.modules.canonical.domain.enums import ObjectFamily, ObjectKind


@dataclass(slots=True)
class CanonicalObject:
    """Address or service object; leaf or group container."""

    id: UUID
    canonical_snapshot_id: UUID
    object_key: str
    object_family: ObjectFamily
    object_kind: ObjectKind
    name: str
    ip_version: int | None
    cidr: str | None
    range_start: str | None
    range_end: str | None
    fqdn: str | None
    protocol: str | None
    port_from: int | None
    port_to: int | None
    icmp_type: int | None
    icmp_code: int | None
    description: str | None

    @classmethod
    def create(
        cls,
        *,
        canonical_snapshot_id: UUID,
        object_key: str,
        object_family: ObjectFamily,
        object_kind: ObjectKind,
        name: str,
        ip_version: int | None = None,
        cidr: str | None = None,
        range_start: str | None = None,
        range_end: str | None = None,
        fqdn: str | None = None,
        protocol: str | None = None,
        port_from: int | None = None,
        port_to: int | None = None,
        icmp_type: int | None = None,
        icmp_code: int | None = None,
        description: str | None = None,
    ) -> CanonicalObject:
        return cls(
            id=uuid4(),
            canonical_snapshot_id=canonical_snapshot_id,
            object_key=object_key,
            object_family=object_family,
            object_kind=object_kind,
            name=name,
            ip_version=ip_version,
            cidr=cidr,
            range_start=range_start,
            range_end=range_end,
            fqdn=fqdn,
            protocol=protocol,
            port_from=port_from,
            port_to=port_to,
            icmp_type=icmp_type,
            icmp_code=icmp_code,
            description=description,
        )


@dataclass(slots=True)
class CanonicalObjectMember:
    id: UUID
    parent_object_id: UUID
    child_object_id: UUID
    position: int

    @classmethod
    def create(
        cls,
        *,
        parent_object_id: UUID,
        child_object_id: UUID,
        position: int = 0,
    ) -> CanonicalObjectMember:
        return cls(
            id=uuid4(),
            parent_object_id=parent_object_id,
            child_object_id=child_object_id,
            position=position,
        )
