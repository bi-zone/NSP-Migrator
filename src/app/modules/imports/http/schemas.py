from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class CreateImportSourceRequest(BaseModel):
    """Request body for creating or reactivating an import source.

    Attributes:
        vendor_code: Vendor identifier supported by the imports pipeline.
        name: Human-readable source name unique within a vendor.
        description: Optional operator-facing source description.
        active: Initial active flag for source visibility in API/UI.
    """

    vendor_code: str = Field(
        min_length=1,
        max_length=64,
        description="Vendor code (for example cisco_asa).",
    )
    name: str = Field(
        min_length=1,
        max_length=255,
        description="Display name of the import source.",
    )
    description: str | None = Field(
        default=None,
        description="Optional free-form description for operators.",
    )
    active: bool = Field(
        default=True,
        description="Whether the source is enabled for new uploads.",
    )


class UploadArtifactRequest(BaseModel):
    """Request body for uploading a raw configuration artifact.

    Attributes:
        file_name: Original filename provided by caller.
        uploaded_by: Username or actor identifier of uploader.
        raw_text: Full raw config payload to parse and index.
        raw_mime_type: Optional MIME type submitted by caller.
        source_format: Parser format hint used by imports pipeline.
    """

    file_name: str = Field(
        min_length=1,
        max_length=512,
        description="Original filename of uploaded configuration artifact.",
    )
    uploaded_by: str = Field(
        min_length=1,
        max_length=128,
        description="Actor identifier (user/service) performing upload.",
    )
    raw_text: str = Field(
        description="Raw configuration text content.",
    )
    raw_mime_type: str | None = Field(
        default=None,
        description="Optional MIME type, e.g. text/plain.",
    )
    source_format: str = Field(
        default="text/plain",
        max_length=64,
        description="Logical source format hint used by parser selection.",
    )


class ImportSourceResponse(BaseModel):
    """API representation of an import source."""

    id: UUID = Field(description="Unique import source identifier.")
    vendor_code: str = Field(description="Vendor code bound to this source.")
    name: str = Field(description="Display name of the source.")
    description: str | None = Field(description="Optional source description.")
    active: bool = Field(description="Whether source is active.")
    created_at: datetime = Field(description="UTC timestamp when source was created.")
    updated_at: datetime = Field(description="UTC timestamp of latest source update.")
    created: bool = Field(
        default=True,
        description="true when source was newly created, false when existing source was returned.",
    )

    model_config = {"from_attributes": True}


class ImportVendorResponse(BaseModel):
    """API representation of a supported import vendor."""

    code: str = Field(description="Stable vendor code used across imports APIs.")
    display_name: str = Field(description="Human-readable vendor name.")
    active: bool = Field(description="Whether vendor is available for new sources.")
    created_at: datetime = Field(description="UTC timestamp when vendor entry was created.")
    updated_at: datetime = Field(description="UTC timestamp of latest vendor update.")

    model_config = {"from_attributes": True}


class SourceSnapshotResponse(BaseModel):
    """API representation of stored source snapshot metadata."""

    id: UUID = Field(description="Snapshot identifier.")
    source_id: UUID | None = Field(description="Owner import source identifier.")
    artifact_hash: str | None = Field(description="Deterministic hash of raw artifact payload.")
    source_format: str | None = Field(description="Declared format hint used by import pipeline.")
    is_latest: bool = Field(description="Latest snapshot marker for given source.")
    created_at: datetime = Field(description="UTC timestamp when snapshot was created.")

    model_config = {"from_attributes": True}


class ImportUploadResponse(BaseModel):
    """API representation of upload processing metadata."""

    id: UUID = Field(description="Upload identifier.")
    source_id: UUID = Field(description="Owner source identifier.")
    file_name: str = Field(description="Original file name from request.")
    uploaded_by: str = Field(description="Actor identifier who uploaded artifact.")
    artifact_hash: str = Field(description="Hash of raw payload used for dedup/idempotency.")
    size_bytes: int = Field(description="Raw payload size in bytes.")
    raw_mime_type: str | None = Field(description="Reported MIME type of uploaded payload.")
    resolved_snapshot_id: UUID | None = Field(
        description="Snapshot linked to upload after dedup or create flow."
    )
    status: str = Field(description="Upload processing status value.")
    created_at: datetime = Field(description="UTC timestamp when upload row was created.")
    consumed_at: datetime | None = Field(
        description="UTC timestamp when downstream processing consumed upload."
    )

    model_config = {"from_attributes": True}


class UploadArtifactResponse(BaseModel):
    """Response payload returned after successful artifact upload.

    Attributes:
        upload: Upload metadata reflecting persistence and status.
        snapshot: Source snapshot metadata linked to uploaded artifact.
    """

    upload: ImportUploadResponse = Field(description="Created upload metadata.")
    snapshot: SourceSnapshotResponse = Field(description="Snapshot metadata resolved for upload.")


class RunCiscoMappingResponse(BaseModel):
    """Response payload for Cisco ASA snapshot-to-canonical mapping run."""

    canonical_snapshot_id: UUID = Field(
        description="Identifier of canonical snapshot produced by mapping flow."
    )


class SourceArtifactRawTextResponse(BaseModel):
    """Raw artifact payload associated with a source snapshot.

    Attributes:
        source_snapshot_id: Source snapshot identifier.
        raw_text: Raw uploaded configuration text.
        line_count: Number of lines in raw text.
        size_bytes: Byte size of raw text payload.
    """

    source_snapshot_id: UUID = Field(description="Source snapshot identifier.")
    raw_text: str = Field(description="Raw configuration text for requested snapshot.")
    line_count: int = Field(description="Total line count of raw text payload.")
    size_bytes: int = Field(description="Payload size in bytes.")

    model_config = {"from_attributes": True}
