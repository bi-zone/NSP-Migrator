from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from app.integrations.sdwan_csp_api.gateways.enums import (
    SdwanAddrObjectType,
    SdwanServiceL4Proto,
)
from app.modules.mapping.domain.enums import (
    CandidateMatchStrategy,
    MappingScopeRuleOperandRole,
)


@dataclass(frozen=True, slots=True)
class MappingScopeRuleOperandPayload:
    """
    Draft payload for creating MappingScopeRuleOperand.

    mapping_entity_result_id:
        Link to already-built mapping result.
    """

    role: MappingScopeRuleOperandRole
    mapping_entity_result_id: UUID


@dataclass(frozen=True, slots=True)
class MappingEntityCandidatePayload:
    """
    Draft payload for candidate (without ID and link to MappingEntity)
    """

    rank: int
    score: int
    strategy: CandidateMatchStrategy
    sdwan_entity_id: int


@dataclass(frozen=True, slots=True)
class CreateAddrObjectPayload:
    type: Literal[
        SdwanAddrObjectType.PREFIX,
        SdwanAddrObjectType.HOST,
        SdwanAddrObjectType.FQDN,
        SdwanAddrObjectType.IP_RANGE,
    ]
    prefix: str | None = None
    host: str | None = None
    fqdn: str | None = None
    ip_range_from: str | None = None
    ip_range_to: str | None = None

    def __post_init__(self):
        if self.type == SdwanAddrObjectType.PREFIX and self.prefix is None:
            raise ValueError("Prefix addr obj must have prefix net")

        if self.type == SdwanAddrObjectType.HOST and self.host is None:
            raise ValueError("Host addr obj must have host address")

        if self.type == SdwanAddrObjectType.FQDN and self.fqdn is None:
            raise ValueError("FQDN addr obj must have fqdn string")

        if self.type == SdwanAddrObjectType.IP_RANGE and (
            self.ip_range_from is None or self.ip_range_to is None
        ):
            raise ValueError("IP Range addr obj must have from and to values")


@dataclass(frozen=True, slots=True)
class CreateServicePayload:
    name: str
    l4_proto: Literal[
        SdwanServiceL4Proto.TCP,
        SdwanServiceL4Proto.UDP,
        SdwanServiceL4Proto.ICMP,
    ]
    port_start: int | None = None
    port_end: int | None = None
    icmp_codes: list[str] | None = None

    def __post_init__(self):
        if self.l4_proto in (SdwanServiceL4Proto.TCP, SdwanServiceL4Proto.UDP) and (
            self.port_start is None or self.port_end is None
        ):
            raise ValueError("TCP/UDP addr obj must have range ports")

        if self.l4_proto == SdwanServiceL4Proto.ICMP and not self.icmp_codes:
            raise ValueError("ICMP addr obj must have codes")
