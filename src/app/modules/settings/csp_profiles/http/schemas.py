from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import UploadFile
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel

from app.modules.settings.csp_profiles.domain.enums import CertificateBundleFormat


async def read_certificate_upload(
    upload: UploadFile,
) -> tuple[bytes, CertificateBundleFormat]:
    filename = upload.filename or ""
    try:
        bundle_format = CertificateBundleFormat.from_filename(filename)
    except ValueError as exc:
        raise _certificate_validation_error(
            "Certificate file must be .pem, .p12, or .pfx"
        ) from exc
    payload = await upload.read()
    if not payload:
        raise _certificate_validation_error("Certificate bundle must not be empty")
    return payload, bundle_format


def _certificate_validation_error(message: str) -> RequestValidationError:
    return RequestValidationError(
        [
            {
                "type": "value_error",
                "loc": ("body", "certificate"),
                "msg": message,
                "input": None,
            }
        ]
    )


class CSPProfileResponse(BaseModel):
    id: UUID
    name: str
    base_url: str
    username: str
    auth_type: str
    has_password: bool
    has_certificate: bool
    certificate_sha256: str
    certificate_not_after: datetime
    certificate_has_private_key: bool
    is_connectable: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CSPProfileSummaryResponse(CSPProfileResponse):
    pass


class AllowedVPCResponse(BaseModel):
    vpc_id: str
    customer_name: str
    project_name: str
    cuid: str
    pid: str

    model_config = {"from_attributes": True}


class TestProfileConnectionResponse(BaseModel):
    reachable: bool
    authenticated: bool
    allowed_vpcs: list[AllowedVPCResponse]
    checked_at: datetime

    model_config = {"from_attributes": True}
