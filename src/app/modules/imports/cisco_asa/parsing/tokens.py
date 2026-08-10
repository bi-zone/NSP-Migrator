from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AclModifiers:
    inactive: bool = False
    log: bool = False
    time_range: str | None = None


def split_tokens(rest: str) -> list[str]:
    return rest.split()


def parse_modifiers(tokens: list[str]) -> tuple[list[str], AclModifiers]:
    lowered = [t.lower() for t in tokens]
    mods = AclModifiers()

    filtered: list[str] = []
    i = 0
    while i < len(tokens):
        t = lowered[i]
        if t == "inactive":
            mods = AclModifiers(inactive=True, log=mods.log, time_range=mods.time_range)
            i += 1
            continue
        if t == "log":
            mods = AclModifiers(
                inactive=mods.inactive, log=True, time_range=mods.time_range
            )
            filtered.append(tokens[i])
            i += 1
            continue
        if t == "time-range" and i + 1 < len(tokens):
            mods = AclModifiers(
                inactive=mods.inactive, log=mods.log, time_range=tokens[i + 1]
            )
            i += 2
            continue
        filtered.append(tokens[i])
        i += 1

    return filtered, mods
