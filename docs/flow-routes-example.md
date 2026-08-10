# ConfigModeProfile Create Flow

Полный путь выполнения сценария создания `ConfigModeProfile`:
от HTTP-запроса до записи в БД и формирования ответа API


## 1) HTTP слой модуля

1. `src/app/modules/settings/config_mode_profile/http/router.py`
   - прописывается endpoint и handler по которому доступен запрос

2. `src/app/modules/settings/config_mode_profile/http/schemas.py`
   - валидация HTTP запроса

3. `http/router.py` внутри handler:
   - `CreateConfigModeProfileCommand.model_validate(body.model_dump())`
   - затем вызывается use-case:
   - `created = await use_case.execute(command)`
   - затем API-ответ:
   - `ConfigModeProfileResponse.model_validate(created.model_dump())`


## 2) Получение use-case через DI

1. `src/app/dependency/use_case_container.py`
   - `get_create_config_mode_profile_use_case(request)`

      берет

     `dependency_graph.use_cases.create_config_mode_profile()`

2. `UseCaseContainer.create_config_mode_profile`
   - создает `CreateConfigModeProfileUseCase`
   - прокидывает `uow=config_mode_profile_uow`

3. `src/app/dependency/uow_container.py`
   - `config_mode_profile_uow = Factory(ConfigModeProfileUnitOfWork, session_factory=...)`

4. `config_mode_profile/adapters/uow.py`
   - в `__aenter__` создается `ConfigModeProfileSqlAlchemyRepository`
   - repository получает `AsyncSession`

## 3) Application use-case (бизнес-сценарий)

Файл:
`config_mode_profile/application/use_cases/create_config_mode_profile.py`

Порядок в `execute(...)`:

1. `ensure_observation_window_allowed(...)`
   (`workflow/domain/rules/observation_window_rules.py`)
   - общий workflow-level здесь общие правила для всех модулей
2. `ConfigModeProfile.create(...)`
   (`config_mode_profile/domain/entities.py`)
   - создается новая доменная сущность
   - генерируются поля нового объекта (например, `id`, `created_at`)
3. `uow.config_mode_profiles.get_by_name(...)`
   - проверка уникальности имени
4. `should_unset_previous_default(profile)`
   (`config_mode_profile/domain/rules/default_profile_rule.py`)
   - доменное правило, которое используется только внутри модуля
   - если `is_default=True`, вызывается `unset_default()`
5. `uow.config_mode_profiles.add(profile)`
   - постановка новой записи на сохранение
6. `to_dto(profile)`
   (`config_mode_profile/application/use_cases/_mapper.py`)
   - преобразование domain entity в application DTO

Транзакция:
`@async_transactional()` (`src/app/shared/transactional.py`)
- открывает UoW (`async with use_case.uow`)
- после успешного `execute` вызывает `uow.commit()`
- при ошибке делает rollback в `AsyncBaseUnitOfWork.__aexit__`

## 4) Repository и маппинг в persistence

1. `config_mode_profile/adapters/repository.py`
   - `add(profile)` вызывает `add_domain(profile)` базового репозитория
2. `src/app/shared/repository.py`
   - `add_domain(entity)` делает:
   - `session.add(mapper.to_model(entity))`
3. `config_mode_profile/adapters/mappers.py`
   - `to_model(entity)` преобразует domain entity -> SQLAlchemy model
4. `config_mode_profile/adapters/models.py`
   - `ConfigModeProfileModel` — ORM модель таблицы `config_mode_profiles`

Важно: `add(...)` не коммитит сам по себе.
Коммит делает UoW в декораторе `@async_transactional()`.

## 7) Краткая карта функций и ролей

- `create` — фабрика нового domain объекта
  - файл: `domain/entities.py`
- `rehydrate` — фабрика восстановления domain объекта из БД
  - файл: `domain/entities.py`
- `to_model` — domain -> ORM
  - файл: `adapters/mappers.py`
- `to_domain` — ORM -> domain (тут вызывается `rehydrate`)
  - файл: `adapters/mappers.py`
- `add` — поставить ORM объект в session
  - файлы: `adapters/repository.py`, `shared/repository.py`
- `to_dto` — domain -> application output DTO
  - файл: `application/use_cases/_mapper.py`
- `ConfigModeProfileResponse` — application DTO -> HTTP response schema
  - файл: `http/router.py`

