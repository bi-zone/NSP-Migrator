"""Canonical object read endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends

from app.modules.canonical.application.use_cases.get_canonical_object import (
    GetCanonicalObjectQuery,
    GetCanonicalObjectUseCase,
)
from app.modules.canonical.application.use_cases.get_canonical_objects import (
    GetCanonicalObjectsQuery,
    GetCanonicalObjectsUseCase,
)
from app.modules.canonical.di.dependencies import (
    get_canonical_object_use_case,
    get_canonical_objects_use_case,
)
from app.modules.canonical.http.schemas import (
    CanonicalObjectDetailResponse,
    CanonicalObjectMemberResponse,
    CanonicalObjectResponse,
)

router = APIRouter(tags=["canonical"])


@router.get(
    "/snapshots/{snapshot_id}/objects",
    response_model=list[CanonicalObjectResponse],
    summary="List snapshot objects",
    description=(
        "Returns all address and service objects for a canonical snapshot. "
        "Group members are not expanded here; use the object detail endpoint "
        "for membership. Returns 404 when the snapshot does not exist."
    ),
)
async def get_snapshot_objects(
    snapshot_id: UUID,
    use_case: GetCanonicalObjectsUseCase = Depends(get_canonical_objects_use_case),
) -> list[CanonicalObjectResponse]:
    result = await use_case.execute(
        GetCanonicalObjectsQuery(canonical_snapshot_id=snapshot_id)
    )
    return [
        CanonicalObjectResponse.model_validate(obj, from_attributes=True)
        for obj in result.objects
    ]


@router.get(
    "/snapshots/{snapshot_id}/objects/{object_id}",
    response_model=CanonicalObjectDetailResponse,
    summary="Get snapshot object with members",
    description=(
        "Returns an object and its ordered group members when the object is a group. "
        "Members list is empty for leaf objects. Returns 404 when the snapshot "
        "or object does not exist."
    ),
)
async def get_snapshot_object(
    snapshot_id: UUID,
    object_id: UUID,
    use_case: GetCanonicalObjectUseCase = Depends(get_canonical_object_use_case),
) -> CanonicalObjectDetailResponse:
    result = await use_case.execute(
        GetCanonicalObjectQuery(
            canonical_snapshot_id=snapshot_id,
            object_id=object_id,
            include_members=True,
        )
    )

    return CanonicalObjectDetailResponse(
        object=CanonicalObjectResponse.model_validate(
            result.object, from_attributes=True
        ),
        members=[
            CanonicalObjectMemberResponse.model_validate(member, from_attributes=True)
            for member in result.members
        ],
    )
