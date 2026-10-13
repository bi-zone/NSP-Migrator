from abc import abstractmethod
from typing import Protocol

from app.modules.settings.csp_profiles.domain.value_objects import CertificateMetadata


class CertificateInspectorPort(Protocol):
    @abstractmethod
    def inspect(self, certificate_pem: str) -> CertificateMetadata: ...
