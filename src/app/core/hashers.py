import hashlib
import json
from dataclasses import dataclass
from typing import Any, Self


def hash_func(value: str) -> str:
    """SHA-256 hash for any string"""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def json_hash(data: Any) -> str:
    """
    Возвращает детерминированный SHA-256 хэш для любого JSON-совместимого объекта.

    Правила:
    - порядок ключей в dict не влияет
    - порядок элементов в list не влияет
    - 1 и 1.0 считаются разными значениями
    """

    def sort_key(obj: Any) -> Any:
        """
        Делает универсальный ключ сортировки для значений JSON,
        чтобы можно было сортировать списки со смешанными типами.
        """
        return json.dumps(
            obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )

    def normalize(obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: normalize(v) for k, v in sorted(obj.items())}

        if isinstance(obj, list):
            normalized_items = [normalize(item) for item in obj]
            return sorted(normalized_items, key=sort_key)

        return str(obj)

    json_str: str = json.dumps(
        normalize(data),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hash_func(json_str)


@dataclass(frozen=True, slots=True)
class HashDataclass:
    """Неизменяемый хеш, полученный из упорядоченного JSON‑содержимого."""

    value: str

    @classmethod
    def from_string(cls, value: str) -> Self:
        return cls(json_hash(value))

    @classmethod
    def from_dicts(cls, *dicts: list[dict]) -> Self:
        """Сортирует ключи рекурсивно, формирует строку и считает SHA‑256."""
        merged = {**{f"_{i}": d for i, d in enumerate(dicts)}}
        return cls(json_hash(merged))
