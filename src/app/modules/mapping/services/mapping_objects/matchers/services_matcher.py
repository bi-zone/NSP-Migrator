from collections import defaultdict

from app.integrations.sdwan_csp_api.gateways.enums import SdwanServiceL4Proto
from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanService,
)
from app.modules.mapping.domain.enums import CandidateMatchStrategy
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalService,
    CanonicalServiceKind,
)
from app.modules.mapping.services.mapping_objects.matchers.utils import (
    CandidateDraft,
    CandidateFinalizer,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.services_catalog_index import (
    SdwanServicesCatalogIndex,
)

_SERVICE_BY_SIGNATURE_SCORE = 100
_SERVICE_BY_BUILTIN_ANY_SCORE = 100
_SERVICE_BY_NAME_SCORE = 70


class ServiceMatcher:
    """
    Matches canonical services to SD-WAN services.
    """

    def __init__(self, catalog_index: SdwanServicesCatalogIndex) -> None:
        self._catalog_index = catalog_index

    def match(self, service: CanonicalService) -> list[MappingEntityCandidatePayload]:
        match service.kind:
            case CanonicalServiceKind.ANY_SERVICE:
                return self._match_any_service(service)

            case CanonicalServiceKind.TCP:
                return self._match_l4_service(
                    service=service,
                    l4_proto=SdwanServiceL4Proto.TCP,
                )

            case CanonicalServiceKind.UDP:
                return self._match_l4_service(
                    service=service,
                    l4_proto=SdwanServiceL4Proto.UDP,
                )

            case CanonicalServiceKind.ICMP:
                return self._match_icmp_service(service)

            case CanonicalServiceKind.IP_PROTO:
                return self._match_ip_proto_service(service)

            case CanonicalServiceKind.SERVICE_GROUP:
                return []

            case _:
                return []

    def _match_any_service(
        self,
        service: CanonicalService,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        for sdwan_service in self._catalog_index.find_builtin_any_services():
            candidates.append(
                self._candidate(
                    sdwan_service,
                    _SERVICE_BY_BUILTIN_ANY_SCORE,
                    CandidateMatchStrategy.BUILTIN_ANY,
                )
            )

        candidates.extend(self._match_by_name(service.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_l4_service(
        self,
        *,
        service: CanonicalService,
        l4_proto: SdwanServiceL4Proto,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        if service.port_from is not None and service.port_to is not None:
            ranges = ((service.port_from, service.port_to),)

            for sdwan_service in self._catalog_index.find_services_by_signature(
                l4_proto=l4_proto,
                ranges=ranges,
            ):
                candidates.append(
                    self._candidate(
                        sdwan_service,
                        _SERVICE_BY_SIGNATURE_SCORE,
                        CandidateMatchStrategy.SERVICE_SIGNATURE,
                    )
                )

        candidates.extend(self._match_by_name(service.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_icmp_service(
        self,
        service: CanonicalService,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        codes = self._canonical_icmp_codes(service)
        if codes:
            for sdwan_service in self._catalog_index.find_icmp_services_by_codes(codes):
                candidates.append(
                    self._candidate(
                        sdwan_service,
                        _SERVICE_BY_SIGNATURE_SCORE,
                        CandidateMatchStrategy.SERVICE_SIGNATURE,
                    )
                )

        candidates.extend(self._match_by_name(service.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_ip_proto_service(
        self,
        service: CanonicalService,
    ) -> list[MappingEntityCandidatePayload]:
        """
        Match IP protocol service. EXPERIMENTAL

        This is intentionally conservative because SD-WAN service representation
        may differ for non-TCP/UDP/ICMP protocols. For now we use only name and
        optional protocol alias.
        """
        candidates = self._match_by_name(service.name)

        if service.protocol:
            for sdwan_service in self._catalog_index.find_services_by_name(
                service.protocol
            ):
                candidates.append(
                    self._candidate(
                        sdwan_service,
                        80,
                        CandidateMatchStrategy.SERVICE_ALIAS,
                    )
                )

        return CandidateFinalizer.finalize(candidates)

    def _match_by_name(self, name: str) -> list[CandidateDraft]:
        # return [
        #     self._candidate(
        #         sdwan_service,
        #         _SERVICE_BY_NAME_SCORE,
        #         CandidateMatchStrategy.NORMALIZED_NAME,
        #     )
        #     for sdwan_service in self._catalog_index.find_services_by_name(name)
        # ]
        # TODO: not using search by name now
        return []

    @staticmethod
    def _canonical_icmp_codes(service: CanonicalService) -> tuple[str, ...]:
        """
        Convert canonical ICMP type/code fields to SD-WAN ICMP code strings.

        SD-WAN stores ICMP services as symbolic message codes, while canonical
        services provide ICMP type and optional code.

        Mapping rules:
        - type + code: exact ICMP message match
        - type only: all known SD-WAN ICMP messages for this ICMP type
        - no type: cannot safely map by signature
        """
        if service.icmp_type is None:
            return ()

        if service.icmp_code is None:
            return _ICMP_SD_WAN_CODES_BY_TYPE.get(service.icmp_type, ())

        sdwan_code = _ICMP_SD_WAN_CODE_BY_TYPE_AND_CODE.get(
            (service.icmp_type, service.icmp_code)
        )
        if sdwan_code is None:
            return ()

        return (sdwan_code,)

    @staticmethod
    def _candidate(
        service: SdwanService,
        score: int,
        strategy: CandidateMatchStrategy,
    ) -> CandidateDraft:
        return CandidateDraft(
            sdwan_entity_id=service.id,
            score=score,
            strategy=strategy,
        )


# -- ICMP helpers
_ICMP_SD_WAN_CODE_BY_TYPE_AND_CODE: dict[tuple[int, int], str] = {
    (0, 0): "echo_reply",
    (3, 0): "network_unreachable",
    (3, 1): "host_unreachable",
    (3, 2): "protocol_unreachable",
    (3, 3): "port_unreachable",
    (3, 4): "fragmentation_needed",
    (3, 5): "source_route_failed",
    (3, 6): "network_unknown",
    (3, 7): "host_unknown",
    (3, 8): "source_host_isolated",
    (3, 9): "network_prohibited",
    (3, 10): "host_prohibited",
    (3, 11): "tos_network_unreachable",
    (3, 12): "tos_host_unreachable",
    (3, 13): "communication_prohibited",
    (3, 14): "host_precedence_violation",
    (3, 15): "precedence_cutoff",
    (5, 0): "network_redirect",
    (5, 1): "host_redirect",
    (5, 2): "tos_network_redirect",
    (5, 3): "tos_host_redirect",
    (8, 0): "echo_request",
    (9, 0): "router_advertisement",
    (9, 16): "does_not_route_common_traffic",
    (10, 0): "router_solicitation",
    (11, 0): "ttl_zero_during_transit",
    (11, 1): "ttl_zero_during_reassembly",
    (12, 0): "ip_header_bad",
    (12, 1): "required_option_missing",
    (12, 2): "bad_length",
    (13, 0): "timestamp_request",
    (14, 0): "timestamp_reply",
}

_ICMP_SD_WAN_CODES_BY_TYPE: dict[int, tuple[str, ...]] = defaultdict(tuple)

_grouped_icmp_codes: dict[int, list[str]] = defaultdict(list)
for (icmp_type, _icmp_code), sdwan_code_ in _ICMP_SD_WAN_CODE_BY_TYPE_AND_CODE.items():
    _grouped_icmp_codes[icmp_type].append(sdwan_code_)

_ICMP_SD_WAN_CODES_BY_TYPE = {
    icmp_type: tuple(codes) for icmp_type, codes in _grouped_icmp_codes.items()
}
