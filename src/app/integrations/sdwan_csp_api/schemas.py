from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_validator


# -- Login schemas
class LoginRequest(BaseModel):
    user: str
    password: str
    vpc_id: str


class LoginResponse(BaseModel):
    token: str
    vpc_id: str


# --


# -- Common rule objects schemas
class CommitEntityDto(BaseModel):  # TODO
    id: int
    kind: str


# -- Commits schemas
class CommitDiffResponse(BaseModel):
    diff_typ: str
    diff_change_typ: str
    user_id: str
    cpe_ids: list[str]
    entity_kind: str | None = None
    entity_id: int | None = None
    new: dict

    model_config = ConfigDict(extra="ignore")


class CommitDataResponse(BaseModel):
    commit_id: int
    name: str
    description: str
    created_at: datetime
    updated_at: datetime | None = None
    user_id: str
    is_applied: bool
    applied_by_task_id: Any
    applied_cpe_ids: Any
    synchronized_cpe_ids: Any

    model_config = ConfigDict(extra="ignore")


class CommitResponse(BaseModel):
    data: CommitDataResponse
    diffs: list[CommitDiffResponse]

    model_config = ConfigDict(extra="ignore")


class ApplyCommitResultResponse(BaseModel):
    success: int
    errors: int
    skipped: int


# --


class ApplyRulesResultResponse(BaseModel):
    commit: CommitResponse
    apply_result: ApplyCommitResultResponse


class CommitRuleObjectsRequest(BaseModel):
    name: str
    description: str = ""
    force: bool = True
    filter: str


# -- Zones schemas
class ZoneResponse(BaseModel):
    id: int
    zone_id: int
    name: str
    typ: str
    vrf_id: Any
    is_permanent: bool
    is_default: bool
    description: str


class ZonesResponse(BaseModel):
    result: list[ZoneResponse]


# -- Service schemas
class ServiceL4Proto(StrEnum):
    TCP = "tcp"
    UDP = "udp"
    ICMP = "icmp"
    ANY = "any"
    IP_IP = "ip_ip"


IcmpCode = Literal[
    "echo_reply",
    "network_unreachable",
    "host_unreachable",
    "protocol_unreachable",
    "port_unreachable",
    "fragmentation_needed",
    "source_route_failed",
    "network_unknown",
    "host_unknown",
    "source_host_isolated",
    "network_prohibited",
    "host_prohibited",
    "tos_network_unreachable",
    "tos_host_unreachable",
    "communication_prohibited",
    "host_precedence_violation",
    "precedence_cutoff",
    "network_redirect",
    "host_redirect",
    "tos_network_redirect",
    "tos_host_redirect",
    "echo_request",
    "router_advertisement",
    "does_not_route_common_traffic",
    "router_solicitation",
    "ttl_zero_during_transit",
    "ttl_zero_during_reassembly",
    "ip_header_bad",
    "required_option_missing",
    "bad_length",
    "timestamp_request",
    "timestamp_reply",
]


class ServicePortRange(BaseModel):
    start: int = Field(ge=0, le=65535)
    end: int = Field(ge=0, le=65535)

    @model_validator(mode="after")
    def validate_range(self):
        if self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class ServiceResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int = Field(validation_alias=AliasChoices("id", "sid"))
    vpc_id: str | None = Field(
        default=None, validation_alias=AliasChoices("vpc_id", "cid")
    )
    name: str
    description: str | None = None
    l4_proto: ServiceL4Proto
    ranges: list[ServicePortRange] | None = None
    codes: list[IcmpCode] | None = None

    @model_validator(mode="after")
    def validate_proto_specific_fields(self):
        if self.l4_proto in ("tcp", "udp"):
            if self.codes is not None:
                raise ValueError("tcp/udp service must not have icmp codes")
            if self.ranges is None:
                raise ValueError("tcp/udp service must have port ranges")

        if self.l4_proto == "icmp":
            if self.ranges is not None:
                raise ValueError("icmp service must not have port ranges")
            if self.codes is None:
                raise ValueError("icmp service must have icmp codes")

        return self


class ServicesResponse(BaseModel):
    data: list[ServiceResponse]


# -- Address objects schemas
class AddrObjectType(StrEnum):

    PREFIX = "prefix"
    HOST = "host"
    FQDN = "fqdn"
    IP_RANGE = "ip_range"
    NETWORK = "network"
    ADDR_GROUP = "addr_group"


class AddrObjectBaseDataResponse(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: AddrObjectType


class AddrObjectPrefixDataResponse(AddrObjectBaseDataResponse):
    type: Literal[AddrObjectType.PREFIX]
    prefix: str
    raw: bool


class AddrObjectHostDataResponse(AddrObjectBaseDataResponse):
    type: Literal[AddrObjectType.HOST]
    host: str
    raw: bool


class AddrObjectFQDNDataResponse(AddrObjectBaseDataResponse):
    type: Literal[AddrObjectType.FQDN]
    fqdn: str
    status: Any
    ips: list[str]


class AddrObjectIPRangeDataResponse(BaseModel):
    type: Literal[AddrObjectType.IP_RANGE]
    from_: str = Field(alias="from")
    to: str
    raw: bool


class AddrObjectNetworkDataResponse(BaseModel):
    type: Literal[AddrObjectType.NETWORK]
    network: str


class AddrObjectAddrGroupDataResponse(BaseModel):
    type: Literal[AddrObjectType.ADDR_GROUP]
    addr_group: int


AddrObjectDataResponse = Annotated[
    AddrObjectPrefixDataResponse
    | AddrObjectFQDNDataResponse
    | AddrObjectHostDataResponse
    | AddrObjectIPRangeDataResponse
    | AddrObjectNetworkDataResponse
    | AddrObjectAddrGroupDataResponse,
    Field(discriminator="type"),
]


class AddrObjectResponse(BaseModel):
    id: int
    parents: list[int]
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    data: AddrObjectDataResponse


class AddrObjectsResponse(BaseModel):
    data: list[AddrObjectResponse]


# -- Networks schemas
class NetworkDhcpConfigResponse(BaseModel):
    sip: str | None = None
    eip: str | None = None
    dns1: str | None = None
    dns2: str | None = None
    dns3: str | None = None
    dhcp_relay_servers: list[str] = Field(default_factory=list)
    dhcp_server_mode: str
    dhcp_client: bool
    ipmac_binds: list[Any] = Field(default_factory=list)
    dhcp_options: list[Any] = Field(default_factory=list)


class NetworkResponse(BaseModel):
    id: int
    network_id: str
    name: str
    cconf_id: str
    vpc_id: str
    vlan: int

    prefix: str | None = None
    ip: str | None = None
    net: str | None = None
    mask: str | None = None
    gw: str | None = None

    announce: bool
    delivered_to_cpe: bool
    version: int
    commited: bool
    deleted: bool
    wan: bool
    typ: str

    public_endpoint: str | None = None
    role: str
    cont_id: str | None = None
    br: str
    dp_port_id: str | None = None
    ns: str | None = None

    dhcp_cfg: NetworkDhcpConfigResponse

    use_as_primary: bool | None = None
    cluster_id: str | None = None
    cluster_net_id: str | None = None
    nat_port_forwarding: Any | None = None

    so_commited: bool
    vrf_id: int | None = None
    zone_id: int | None = None

    actual_ips: list[str] = Field(default_factory=list)

    pbr_id: str | None = None
    tc_policy_id: str | None = None

    metric: int | None = None
    gw_metric: int | None = None
    mac: str | None = None

    secondary_ips: list[str] = Field(default_factory=list)


class NetworksResponse(BaseModel):
    result: list[NetworkResponse]


# -- Address object create schemas
class CreateAddrObjectPrefixRequestData(BaseModel):
    type: Literal["prefix"] = "prefix"
    prefix: str
    raw: bool = False


class CreateAddrObjectHostRequestData(BaseModel):
    type: Literal["host"] = "host"
    host: str
    raw: bool = False


class CreateAddrObjectFqdnRequestData(BaseModel):
    type: Literal["fqdn"] = "fqdn"
    fqdn: str
    raw: bool = False


class CreateAddrObjectIpRangeRequestData(BaseModel):
    type: Literal["ip_range"] = "ip_range"
    from_: str = Field(serialization_alias="from")
    to: str
    raw: bool = False


CreateAddrObjectRequestData = Annotated[
    CreateAddrObjectPrefixRequestData
    | CreateAddrObjectHostRequestData
    | CreateAddrObjectFqdnRequestData
    | CreateAddrObjectIpRangeRequestData,
    Field(discriminator="type"),
]


class CreateAddrObjectRequest(BaseModel):
    description: str = ""
    data: CreateAddrObjectRequestData


# --


# -- Service create schema
class ServiceCreateRequest(BaseModel):

    model_config = ConfigDict(
        extra="ignore",
    )

    name: str
    description: str | None = None
    l4_proto: ServiceL4Proto
    ranges: list[ServicePortRange] | None = None
    codes: list[IcmpCode] | None = None

    @model_validator(mode="after")
    def validate_proto_specific_fields(self):
        if self.l4_proto in ("tcp", "udp"):
            if self.codes is not None:
                raise ValueError("tcp/udp service must not have icmp codes")
            if self.ranges is None:
                raise ValueError("tcp/udp service must have port ranges")

        if self.l4_proto == "icmp":
            if self.ranges is not None:
                raise ValueError("icmp service must not have port ranges")
            if self.codes is None:
                raise ValueError("icmp service must have icmp codes")

        return self


# --


# -- CPE info schemas
class CPEInfoResponse(BaseModel):

    model_config = ConfigDict(
        extra="ignore",
    )

    id: int
    cpe_id: str
    cconf_id: str
    vpc_id: str
    sid: str | None
    name: str
    description: str


# --


# -- Device Object Schemas
DeviceObjectId = str


class CConfInfoResponse(BaseModel):

    model_config = ConfigDict(
        extra="ignore",
    )

    id: int
    cconf_id: str
    vpc_id: str
    index_number: int
    typ: str
    cconft_id: str
    priority: int
    deleted: bool


class DeviceObjectResponse(BaseModel):

    model_config = ConfigDict(
        extra="ignore",
    )

    id: int
    dev_obj_id: DeviceObjectId
    parent_dev_obj_ids: list[DeviceObjectId]
    vpc_id: str
    type: Literal["group", "device"]
    name: str
    description: str | None
    depth: int
    created_at: float
    updated_at: float | None
    is_global: bool
    cpe: CPEInfoResponse | None  # None for group
    cconf: CConfInfoResponse | None  # None for group
    cpe_cluster: list[Any]


# --


# -- Policies schemas
class RuleAction(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    DROP = "DROP"


class AddrObject(BaseModel):
    type: AddrObjectType
    id: int


class AmbiguousReason(BaseModel):
    code: int
    meta: dict


class PolicyResponse(BaseModel):
    type: Literal["policy"]  # ignore null_policy
    policy_id: int
    parents: list[DeviceObjectId]
    order: str
    priority: Literal["pre", "local", "post"]
    name: str
    description: str
    tags: list[str]
    activated: bool
    action: RuleAction
    log: bool
    l4_inspection: bool
    ambiguous: bool
    ambiguous_reason: AmbiguousReason | None
    created_at: str
    updated_at: str
    snat: dict | None
    dnat: dict | None

    ingress_zone: list[int]
    egress_zone: list[int]

    src_address: list[AddrObject]
    dst_address: list[AddrObject]

    service: list[int]

    src_idents: list[Any]
    dst_idents: list[Any]


class CreatePolicyRequest(BaseModel):
    name: str
    description: str = ""
    tags: list[str]
    activated: bool
    action: RuleAction
    log: bool
    l4_inspection: bool
    ingress_zone: list[int]
    egress_zone: list[int]
    src_address: list[int]
    dst_address: list[int]
    service: list[int]
    parent: DeviceObjectId
    parent_type: Literal["device"]
    priority: str = "local"
    policy_position: dict = {"position": "tail"}


# --
