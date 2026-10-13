from dataclasses import dataclass, replace
from uuid import UUID

from app.infrastructure.interfaces.cache import RuntimeCacheStorePort
from app.modules.mapping.domain.entities import (
    MappingEntityResult,
    MappingScope,
    MappingScopeRule,
    MappingScopeRuleOperand,
)
from app.modules.mapping.domain.enums import (
    MappingEntityType,
    MappingResultStatus,
)
from app.modules.mapping.ports.repositories import MappingRepositoryPort

_MAPPING_SCOPE_NAMESPACE = "mapping.scope"


@dataclass(frozen=True, slots=True)
class _MappingScopeCacheEntry:
    scope: MappingScope
    rules: dict[UUID, MappingScopeRule]
    results: dict[UUID, MappingEntityResult]


class RuntimeCacheMappingRepository(MappingRepositoryPort):
    """
    Runtime-cache repository over one mapping scope graph entry.

    The implementation performs synchronous in-process cache operations under
    the hood. Public methods stay async to satisfy the module repository port
    and keep application use cases independent from the current storage backend:
    the same port can later be backed by async storage without changing callers.
    """

    def __init__(self, cache_store: RuntimeCacheStorePort) -> None:
        self._cache_store = cache_store

    def _require_scope_entry(self, scope_id: UUID) -> _MappingScopeCacheEntry:
        entry = self._get_scope_entry(scope_id, touch=True)
        if entry is None:
            raise ValueError("Mapping scope not found")
        return entry

    def _get_scope_entry(
        self,
        scope_id: UUID,
        *,
        touch: bool,
    ) -> _MappingScopeCacheEntry | None:
        return self._cache_store.get(
            _MAPPING_SCOPE_NAMESPACE,
            scope_id,
            touch=touch,
        )

    def _set_scope_entry(self, scope_id: UUID, entry: _MappingScopeCacheEntry) -> None:
        self._cache_store.set(
            _MAPPING_SCOPE_NAMESPACE,
            scope_id,
            entry,
        )

    def _iter_scope_entries(self, *, touch: bool) -> list[_MappingScopeCacheEntry]:
        entries = []
        for key in self._cache_store.keys(_MAPPING_SCOPE_NAMESPACE):
            entry = self._cache_store.get(
                _MAPPING_SCOPE_NAMESPACE,
                key,
                touch=touch,
            )
            if entry is not None:
                entries.append(entry)

        return entries

    async def add_scope(self, scope: MappingScope) -> MappingScope:
        if self._get_scope_entry(scope.id, touch=False) is not None:
            raise ValueError(f"Mapping scope {scope.id} already exists")

        self._set_scope_entry(
            scope_id=scope.id,
            entry=_MappingScopeCacheEntry(
                scope=scope,
                rules={},
                results={},
            ),
        )
        return scope

    async def get_scope_by_id(
        self,
        scope_id: UUID,
        *,
        with_rules: bool = False,
    ) -> MappingScope | None:
        entry = self._get_scope_entry(scope_id, touch=True)
        if entry is None:
            return None

        return self._materialize_scope(entry)

    async def refresh_catalog_fingerprint(
        self,
        *,
        scope_id: UUID,
        catalog_fingerprint: str,
    ) -> MappingScope:
        entry = self._require_scope_entry(scope_id)
        scope = entry.scope.refresh_catalog_fingerprint(catalog_fingerprint)
        self._set_scope_entry(scope_id, replace(entry, scope=scope))
        return self._materialize_scope(replace(entry, scope=scope))

    async def attach_rules(
        self,
        *,
        scope_id: UUID,
        rules: list[MappingScopeRule],
    ) -> None:
        entry = self._require_scope_entry(scope_id)

        if not rules:
            return

        for rule in rules:
            if rule.mapping_scope_id != scope_id:
                raise ValueError("MappingScopeRule belongs to another scope")
            if rule.id in entry.rules:
                raise ValueError(f"Mapping scope rule {rule.id} already exists")

        updated_rules = dict(entry.rules)
        updated_rules.update({rule.id: rule for rule in rules})
        self._set_scope_entry(
            scope_id,
            replace(entry, rules=updated_rules),
        )

    async def add_rule_operand(
        self,
        *,
        scope_id: UUID,
        operand: MappingScopeRuleOperand,
    ) -> None:
        entry = self._require_scope_entry(scope_id)
        rule = entry.rules.get(operand.mapping_scope_rule_id)
        if rule is None:
            raise ValueError("MappingScopeRule does not belong to provided scope")

        operands = list(rule.operands or [])
        operands.append(operand)

        updated_rules = dict(entry.rules)
        updated_rules[rule.id] = replace(rule, operands=operands)
        self._set_scope_entry(
            scope_id,
            replace(entry, rules=updated_rules),
        )

    async def list_recent_scopes(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> list[MappingScope]:
        scopes = sorted(
            map(self._materialize_scope, self._iter_scope_entries(touch=False)),
            key=lambda scope: scope.created_at,
            reverse=True,
        )
        return scopes[offset : offset + limit]

    @staticmethod
    def _materialize_scope(entry: _MappingScopeCacheEntry) -> MappingScope:
        return replace(
            entry.scope,
            rules=sorted(entry.rules.values(), key=lambda rule: rule.priority),
        )

    async def add_results(
        self,
        scope_id: UUID,
        results: list[MappingEntityResult],
    ) -> None:
        entry = self._require_scope_entry(scope_id)

        if not results:
            return

        for result in results:
            if result.mapping_scope_id != scope_id:
                raise ValueError("MappingEntityResult belongs to another scope")
            if result.id in entry.results:
                raise ValueError(f"Mapping entity result {result.id} already exists")

        updated_results = entry.results | {result.id: result for result in results}
        self._set_scope_entry(
            scope_id,
            replace(entry, results=updated_results),
        )

    async def get_result(
        self,
        scope_id: UUID,
        result_id: UUID,
        *,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        entry = self._get_scope_entry(scope_id, touch=True)
        if entry is None:
            return None

        return entry.results.get(result_id, None)

    async def find_result_by_canonical_entity(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType,
        canonical_entity_id: UUID,
        with_candidates: bool = False,
    ) -> MappingEntityResult | None:
        entry = self._get_scope_entry(scope_id, touch=True)
        if entry is None:
            return None

        def _eq_canonical_entity_id(result: MappingEntityResult) -> bool:
            try:
                return canonical_entity_id == result.canonical_entity_id
            except ValueError:
                if result.entity_type != MappingEntityType.ZONE:
                    raise
                return False

        matches = [
            result
            for result in entry.results.values()
            if (result.entity_type == entity_type and _eq_canonical_entity_id(result))
        ]

        if len(matches) > 1:
            raise ValueError(
                f"Found {len(matches)} mapping results for canonical entity"
            )
        elif len(matches) == 0:
            return None
        else:
            return matches[0]

    async def list_results(
        self,
        *,
        scope_id: UUID,
        entity_type: MappingEntityType | None = None,
        status: MappingResultStatus | None = None,
        with_candidates: bool = False,
    ) -> list[MappingEntityResult]:
        entry = self._get_scope_entry(scope_id, touch=True)
        if entry is None:
            return []

        return sorted(
            (
                result
                for result in entry.results.values()
                if (entity_type is None or result.entity_type == entity_type)
                and (status is None or result.result_status == status)
            ),
            key=lambda result: (result.entity_type, result.created_at),
        )

    async def save_result(self, result: MappingEntityResult) -> MappingEntityResult:
        entry = self._require_scope_entry(result.mapping_scope_id)
        current = entry.results.get(result.id)
        if current is None:
            raise ValueError("Mapping entity result not found")

        candidates = (
            current.candidates if result.candidates is None else result.candidates
        )
        saved = replace(result, candidates=candidates)
        if saved == current:
            return saved

        updated_results = dict(entry.results)
        updated_results[result.id] = saved
        self._set_scope_entry(
            result.mapping_scope_id,
            replace(entry, results=updated_results),
        )
        return saved
