from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LineSpan:
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class ConfigLine:
    line_no: int
    text: str
    indent: int

    @property
    def stripped(self) -> str:
        return self.text.strip()
