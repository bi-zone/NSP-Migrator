"""Public Cisco ASA parser/normalizer contracts."""

from app.modules.imports.cisco_asa.ports.normalizer import CiscoAsaNormalizerPort
from app.modules.imports.cisco_asa.ports.parser import CiscoAsaParserPort

__all__ = [
    "CiscoAsaNormalizerPort",
    "CiscoAsaParserPort",
]
