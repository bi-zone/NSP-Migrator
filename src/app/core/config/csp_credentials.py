import base64
import binascii
from typing import Self

from pydantic import BaseModel, ConfigDict, SecretBytes, SecretStr


class CSPCredentialsConfig(BaseModel):
    """Validated external key used by the CSP."""

    model_config = ConfigDict(frozen=True)

    active_key: SecretBytes

    @classmethod
    def from_settings(cls, active_key: SecretStr) -> Self:
        return cls(active_key=SecretBytes(_decode_key(active_key.get_secret_value())))


def _decode_key(encoded_key: str) -> bytes:
    try:
        key = base64.b64decode(encoded_key, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError("CSP master key must be valid base64") from exc
    if len(key) != 32:
        raise ValueError("CSP master key must decode to 32 bytes")
    return key
