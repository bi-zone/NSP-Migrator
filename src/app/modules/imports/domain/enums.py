from __future__ import annotations

from enum import StrEnum


class VendorCode(StrEnum):
    CISCO_ASA = "cisco_asa"


class UploadStatus(StrEnum):
    RECEIVED = "received"
    RESOLVED = "resolved"
    FAILED = "failed"
