from abc import abstractmethod
from typing import Protocol

from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO


class CertificateBundleConverterPort(Protocol):
    @abstractmethod
    def convert(self, bundle: CertificateBundleDTO) -> str: ...
