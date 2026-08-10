from fastapi import Depends, Request

from app.di.dependencies import get_di_container
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingUseCase,
)
from app.modules.imports.cisco_asa.di.container import CiscoAsaModuleContainer


def get_cisco_asa_module_container(request: Request) -> CiscoAsaModuleContainer:
    return get_di_container(request).cisco_asa_module()


def get_run_cisco_mapping_use_case(
    module_container: CiscoAsaModuleContainer = Depends(get_cisco_asa_module_container),
) -> RunCiscoMappingUseCase:
    return module_container.run_cisco_mapping_use_case()
