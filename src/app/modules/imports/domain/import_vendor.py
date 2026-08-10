from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class ImportVendor:
    code: str
    display_name: str
    active: bool
    created_at: datetime
    updated_at: datetime
