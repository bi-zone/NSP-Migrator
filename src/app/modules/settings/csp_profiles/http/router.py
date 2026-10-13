from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from fastapi.exceptions import RequestValidationError

from app.modules.settings.csp_profiles.application.check_profile_connection import (
    TestProfileConnectionCommand,
    TestProfileConnectionUseCase,
)
from app.modules.settings.csp_profiles.application.create_profile import (
    CreateProfileCommand,
    CreateProfileUseCase,
)
from app.modules.settings.csp_profiles.application.delete_profile import (
    DeleteProfileCommand,
    DeleteProfileUseCase,
)
from app.modules.settings.csp_profiles.application.dto import CertificateBundleDTO
from app.modules.settings.csp_profiles.application.get_profile import (
    GetProfileQuery,
    GetProfileUseCase,
)
from app.modules.settings.csp_profiles.application.list_profiles import (
    ListProfilesQuery,
    ListProfilesUseCase,
)
from app.modules.settings.csp_profiles.application.remove_profile_password import (
    RemoveProfilePasswordCommand,
    RemoveProfilePasswordUseCase,
)
from app.modules.settings.csp_profiles.application.update_profile import (
    UNSET,
    UnsetType,
    UpdateProfileCommand,
    UpdateProfileUseCase,
)
from app.modules.settings.csp_profiles.di.dependencies import (
    create_profile_uc,
    delete_profile_uc,
    get_profile_uc,
    list_profiles_uc,
    remove_profile_password_uc,
    test_profile_connection_uc,
    update_profile_uc,
)
from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat
from app.modules.settings.csp_profiles.http.schemas import (
    CSPProfileResponse,
    CSPProfileSummaryResponse,
    TestProfileConnectionResponse,
    read_certificate_upload,
)

router = APIRouter(prefix="/csp-profiles", tags=["settings"])


@router.post("", status_code=status.HTTP_201_CREATED, response_model=CSPProfileResponse)
async def create_profile(
    name: Annotated[str, Form(min_length=1, max_length=128)],
    base_url: Annotated[str, Form(min_length=1)],
    username: Annotated[str, Form(min_length=1, max_length=255)],
    password: Annotated[str, Form(min_length=1)],
    certificate: Annotated[UploadFile, File()],
    certificate_passphrase: Annotated[str | None, Form()] = None,
    use_case: CreateProfileUseCase = Depends(create_profile_uc),
) -> CSPProfileResponse:
    bundle_data, bundle_format = await read_certificate_upload(certificate)
    result = await use_case.execute(
        CreateProfileCommand(
            name=name,
            base_url=base_url,
            username=username,
            password=password,
            certificate_bundle=CertificateBundleDTO(
                data=bundle_data,
                format=bundle_format,
                passphrase=_optional_passphrase(certificate_passphrase),
            ),
        )
    )
    return CSPProfileResponse.model_validate(result)


@router.get("", response_model=list[CSPProfileSummaryResponse])
async def list_profiles(
    active_only: bool = Query(default=False, description="Get only active profiles"),
    use_case: ListProfilesUseCase = Depends(list_profiles_uc),
) -> list[CSPProfileSummaryResponse]:
    result = await use_case.execute(query=ListProfilesQuery(active_only=active_only))
    return [
        CSPProfileSummaryResponse.model_validate(profile) for profile in result.profiles
    ]


@router.get("/{profile_id}", response_model=CSPProfileResponse)
async def get_profile(
    profile_id: UUID,
    use_case: GetProfileUseCase = Depends(get_profile_uc),
) -> CSPProfileResponse:
    result = await use_case.execute(GetProfileQuery(profile_id=profile_id))
    return CSPProfileResponse.model_validate(result)


@router.patch("/{profile_id}", response_model=CSPProfileResponse)
async def update_profile(
    profile_id: UUID,
    response: Response,
    name: Annotated[str | None, Form(min_length=1, max_length=128)] = None,
    base_url: Annotated[str | None, Form(min_length=1)] = None,
    username: Annotated[str | None, Form(min_length=1, max_length=255)] = None,
    password: Annotated[str | None, Form(min_length=1)] = None,
    certificate_passphrase: Annotated[str | None, Form()] = None,
    certificate: Annotated[UploadFile | None, File()] = None,
    use_case: UpdateProfileUseCase = Depends(update_profile_uc),
) -> CSPProfileResponse:
    certificate_data, certificate_format = await _patch_certificate(certificate)
    result = await use_case.execute(
        UpdateProfileCommand(
            profile_id=profile_id,
            name=_patch_form_value(name),
            base_url=_patch_form_value(base_url),
            username=_patch_form_value(username),
            password=_patch_form_value(password),
            certificate_bundle=CertificateBundleDTO(
                data=certificate_data,  # type: ignore
                format=certificate_format,  # type: ignore
                passphrase=_patch_passphrase(
                    value=certificate_passphrase,
                    has_certificate=certificate is not None,
                ),
            )
            if certificate_data is not UNSET
            else UNSET,
        )
    )
    return CSPProfileResponse.model_validate(result)


@router.delete(
    "/{profile_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_profile(
    profile_id: UUID,
    use_case: DeleteProfileUseCase = Depends(delete_profile_uc),
) -> Response:
    await use_case.execute(DeleteProfileCommand(profile_id=profile_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/{profile_id}/credentials/password",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_profile_password(
    profile_id: UUID,
    response: Response,
    use_case: RemoveProfilePasswordUseCase = Depends(remove_profile_password_uc),
) -> Response:
    await use_case.execute(RemoveProfilePasswordCommand(profile_id=profile_id))
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post(
    "/{profile_id}/test-connection",
    response_model=TestProfileConnectionResponse,
)
async def test_profile_connection(
    profile_id: UUID,
    use_case: TestProfileConnectionUseCase = Depends(test_profile_connection_uc),
) -> TestProfileConnectionResponse:
    result = await use_case.execute(TestProfileConnectionCommand(profile_id=profile_id))
    return TestProfileConnectionResponse.model_validate(result)


async def _patch_certificate(
    upload: UploadFile | None,
) -> tuple[UnsetType, UnsetType] | tuple[bytes, CertificateBundleFormat]:
    if upload is None:
        return UNSET, UNSET
    bundle, bundle_format = await read_certificate_upload(upload)
    return bundle, bundle_format


def _patch_form_value(value: str | None) -> Any:
    return UNSET if value is None else value


def _patch_passphrase(value: str | None, *, has_certificate: bool) -> Any:
    if value is None:
        return UNSET
    if not value.strip() or not has_certificate:
        raise _passphrase_requires_certificate()
    return value


def _optional_passphrase(value: str | None) -> str | None:
    if value is None or not value.strip():
        return None
    return value


def _passphrase_requires_certificate() -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "certificate_passphrase"),
                "msg": "Certificate passphrase requires a new certificate file",
                "input": None,
            }
        ]
    )
