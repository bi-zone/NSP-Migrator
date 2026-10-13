"""Database seed helpers for focused module integration fixtures.

These helpers are intentionally plain functions, not global pytest fixtures.
Module-level conftests can wrap them when a specific module needs canonical or
mapping rows for foreign-key checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True, slots=True)
class CanonicalSnapshotGraphIds:
    """Parent FK ids required by canonical and trace child tables."""

    source_snapshot_id: UUID
    canonical_snapshot_id: UUID


async def seed_canonical_snapshot_graph(
    session: AsyncSession,
    *,
    label: str = "primary",
) -> CanonicalSnapshotGraphIds:
    """Create the smallest valid import/source/canonical snapshot graph."""
    token = uuid4().hex[:8]
    vendor_code = f"test-vendor-{token}"
    source_id = uuid4()
    source_snapshot_id = uuid4()
    canonical_snapshot_id = uuid4()
    await session.execute(
        text("""
            INSERT INTO import_vendor
                (code, display_name, active)
            VALUES
                (:vendor_code, :display_name, true)
            """),
        {"vendor_code": vendor_code, "display_name": f"Test Vendor {label}"},
    )
    await session.execute(
        text("""
            INSERT INTO import_source
                (id, vendor_code, name, description, active)
            VALUES
                (:source_id, :vendor_code, :name, NULL, true)
            """),
        {
            "source_id": source_id,
            "vendor_code": vendor_code,
            "name": f"Test Source {label}-{token}",
        },
    )
    await session.execute(
        text("""
            INSERT INTO source_snapshot
                (id, source_id, artifact_hash, source_format, is_latest)
            VALUES
                (:source_snapshot_id, :source_id, :artifact_hash, 'cisco_asa', true)
            """),
        {
            "source_snapshot_id": source_snapshot_id,
            "source_id": source_id,
            "artifact_hash": token.ljust(64, "0"),
        },
    )
    await session.execute(
        text("""
            INSERT INTO canonical_snapshot
                (
                    id,
                    source_snapshot_id,
                    normalizer_code,
                    normalizer_version,
                    status,
                    zones_total,
                    objects_total,
                    rules_total,
                    issues_total
                )
            VALUES
                (
                    :canonical_snapshot_id,
                    :source_snapshot_id,
                    'test-normalizer',
                    :normalizer_version,
                    'success',
                    0,
                    0,
                    0,
                    0
                )
            """),
        {
            "canonical_snapshot_id": canonical_snapshot_id,
            "source_snapshot_id": source_snapshot_id,
            "normalizer_version": f"1-{label}-{token}",
        },
    )
    await session.commit()
    return CanonicalSnapshotGraphIds(
        source_snapshot_id=source_snapshot_id,
        canonical_snapshot_id=canonical_snapshot_id,
    )
