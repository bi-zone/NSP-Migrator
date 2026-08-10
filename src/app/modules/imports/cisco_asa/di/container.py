from dependency_injector import providers
from dependency_injector.containers import DeclarativeContainer

from app.modules.imports.cisco_asa.adapters.normalizer import CiscoAsaNormalizerAdapter
from app.modules.imports.cisco_asa.adapters.parser import CiscoAsaParserAdapter
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_import import (
    RunCiscoImportUseCase,
)
from app.modules.imports.cisco_asa.application.use_cases.run_cisco_mapping import (
    RunCiscoMappingUseCase,
)


class CiscoAsaModuleContainer(DeclarativeContainer):
    imports_module = providers.DependenciesContainer()
    canonical_module = providers.DependenciesContainer()
    trace_module = providers.DependenciesContainer()

    parser = providers.Singleton(CiscoAsaParserAdapter)
    normalizer = providers.Singleton(CiscoAsaNormalizerAdapter)

    run_cisco_import_use_case = providers.Factory(
        RunCiscoImportUseCase,
        uow=imports_module.uow,
        parser=parser,
    )

    run_cisco_mapping_use_case = providers.Factory(
        RunCiscoMappingUseCase,
        uow=imports_module.uow,
        parser=parser,
        normalizer=normalizer,
        save_canonical_snapshot=canonical_module.save_canonical_snapshot_use_case,
        save_trace_records=trace_module.save_trace_records_use_case,
    )
