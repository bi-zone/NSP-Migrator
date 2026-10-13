from dataclasses import dataclass

from app.modules.canonical.application.dto import CanonicalObjectDTO
from app.modules.canonical.domain.enums import ObjectFamily
from app.modules.trace.application.dto import TraceRecordDTO


@dataclass(frozen=True, slots=True)
class CanonicalObjectEvidence:
    canonical_object: CanonicalObjectDTO
    trace_records: list[TraceRecordDTO]


@dataclass(frozen=True, slots=True)
class CanonicalObjectFieldRow:
    field: str
    value: str


def build_canonical_object_field_rows(
    obj: CanonicalObjectDTO,
) -> list[CanonicalObjectFieldRow]:
    fields: list[tuple[str, object | None]] = [
        ("Canonical ID", obj.id),
        ("Object key", obj.object_key),
        ("Name", obj.name),
        ("Family", obj.object_family),
        ("Kind", obj.object_kind),
    ]

    if obj.object_family == ObjectFamily.ADDR:
        fields.extend(
            [
                ("IP version", obj.ip_version),
                ("CIDR", obj.cidr),
                ("Range start", obj.range_start),
                ("Range end", obj.range_end),
                ("FQDN", obj.fqdn),
            ]
        )
    elif obj.object_family == ObjectFamily.SERVICE:
        fields.extend(
            [
                ("Protocol", obj.protocol),
                ("Port from", obj.port_from),
                ("Port to", obj.port_to),
                ("ICMP type", obj.icmp_type),
                ("ICMP code", obj.icmp_code),
            ]
        )

    fields.append(("Description", obj.description))

    return [
        CanonicalObjectFieldRow(field=field, value=str(value))
        for field, value in fields
        if value is not None and value != ""
    ]
