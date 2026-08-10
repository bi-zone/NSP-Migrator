from ipaddress import IPv4Address, IPv4Network

from app.integrations.sdwan_csp_api.gateways.models import (
    SdwanAddrObject,
)
from app.modules.mapping.domain.enums import CandidateMatchStrategy
from app.modules.mapping.domain.value_objects import MappingEntityCandidatePayload
from app.modules.mapping.ports.canonical_reader.schemas import (
    CanonicalAddrObject,
    CanonicalAddrObjKind,
)
from app.modules.mapping.services.mapping_objects.matchers.utils import (
    CandidateDraft,
    CandidateFinalizer,
)
from app.modules.mapping.services.mapping_objects.sdwan_catalog_indexes.addr_objs_catalog_index import (
    SdwanAddrObjsCatalogIndex,
)

_ADDR_OBJ_BY_BUILTIN_ANY_SCORE = 100
_ADDR_OBJ_BY_EXACT_VALUE_SCORE = 100
_ADDR_OBJ_BY_NAME_SCORE = 70


class AddrObjectMatcher:
    """
    Matches canonical address objects to SD-WAN address objects.
    """

    def __init__(self, catalog_index: SdwanAddrObjsCatalogIndex) -> None:
        self._catalog_index = catalog_index

    def match(self, obj: CanonicalAddrObject) -> list[MappingEntityCandidatePayload]:
        match obj.kind:
            case CanonicalAddrObjKind.ANY_ADDR:
                return self._match_any_addr(obj)

            case CanonicalAddrObjKind.HOST:
                return self._match_host(obj)

            case CanonicalAddrObjKind.SUBNET:
                return self._match_subnet(obj)

            case CanonicalAddrObjKind.RANGE:
                return self._match_range(obj)

            case CanonicalAddrObjKind.FQDN:
                return self._match_fqdn(obj)

            # case CanonicalAddrObjKind.ADDR_GROUP:  # TODO: addr groups later, now only flat objects array
            #     return []

            case CanonicalAddrObjKind.UNRESOLVED_SERVICE:
                return []

            case _:
                return []

    def _match_any_addr(
        self,
        obj: CanonicalAddrObject,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        for sdwan_obj in self._catalog_index.find_builtin_any_addr_objects():
            candidates.append(
                self._candidate(
                    sdwan_obj,
                    _ADDR_OBJ_BY_BUILTIN_ANY_SCORE,
                    CandidateMatchStrategy.BUILTIN_ANY,
                )
            )

        # Name fallback. Sometimes imported canonical "any" is represented only by name.
        candidates.extend(self._match_by_name(obj.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_host(
        self,
        obj: CanonicalAddrObject,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        if obj.cidr:
            try:
                host = IPv4Address(obj.cidr.split("/")[0])
            except ValueError:
                return CandidateFinalizer.finalize(self._match_by_name(obj.name))

            for sdwan_obj in self._catalog_index.find_addr_by_host(host):
                candidates.append(
                    self._candidate(
                        sdwan_obj,
                        _ADDR_OBJ_BY_EXACT_VALUE_SCORE,
                        CandidateMatchStrategy.EXACT_VALUE,
                    )
                )

        candidates.extend(self._match_by_name(obj.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_subnet(
        self,
        obj: CanonicalAddrObject,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        if obj.cidr:
            try:
                prefix = IPv4Network(obj.cidr, strict=False)
            except ValueError:
                return CandidateFinalizer.finalize(self._match_by_name(obj.name))

            for sdwan_obj in self._catalog_index.find_addr_by_prefix(prefix):
                candidates.append(
                    self._candidate(
                        sdwan_obj,
                        _ADDR_OBJ_BY_EXACT_VALUE_SCORE,
                        CandidateMatchStrategy.EXACT_VALUE,
                    )
                )

        candidates.extend(self._match_by_name(obj.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_range(
        self,
        obj: CanonicalAddrObject,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        if obj.range_start and obj.range_end:
            try:
                range_start = IPv4Address(obj.range_start)
                range_end = IPv4Address(obj.range_end)
            except ValueError:
                return CandidateFinalizer.finalize(self._match_by_name(obj.name))

            for sdwan_obj in self._catalog_index.find_addr_by_range(
                range_start,
                range_end,
            ):
                candidates.append(
                    self._candidate(
                        sdwan_obj,
                        _ADDR_OBJ_BY_EXACT_VALUE_SCORE,
                        CandidateMatchStrategy.EXACT_VALUE,
                    )
                )

        candidates.extend(self._match_by_name(obj.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_fqdn(
        self,
        obj: CanonicalAddrObject,
    ) -> list[MappingEntityCandidatePayload]:
        candidates: list[CandidateDraft] = []

        if obj.fqdn:
            for sdwan_obj in self._catalog_index.find_addr_by_fqdn(obj.fqdn):
                candidates.append(
                    self._candidate(
                        sdwan_obj,
                        _ADDR_OBJ_BY_EXACT_VALUE_SCORE,
                        CandidateMatchStrategy.EXACT_VALUE,
                    )
                )

        candidates.extend(self._match_by_name(obj.name))

        return CandidateFinalizer.finalize(candidates)

    def _match_by_name(self, name: str) -> list[CandidateDraft]:
        # return [
        #     self._candidate(
        #         sdwan_obj,
        #         _ADDR_OBJ_BY_NAME_SCORE,
        #         CandidateMatchStrategy.NORMALIZED_NAME,
        #     )
        #     for sdwan_obj in self._catalog_index.find_addr_by_name(name)
        # ]
        # TODO: not using search by name now
        return []

    @staticmethod
    def _candidate(
        obj: SdwanAddrObject,
        score: int,
        strategy: CandidateMatchStrategy,
    ) -> CandidateDraft:
        return CandidateDraft(
            sdwan_entity_id=obj.id,
            score=score,
            strategy=strategy,
        )
