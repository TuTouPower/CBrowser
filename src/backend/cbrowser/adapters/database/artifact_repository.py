"""SQLite repository for Artifact metadata; the API is the only writer."""

from __future__ import annotations

import uuid

from cbrowser.adapters.database.models import (
    ArtifactModel,
    ProfileModel,
    ProfileRuntimeModel,
    RuntimeEventModel,
)
from cbrowser.adapters.database.session import write_transaction
from cbrowser.domain.models import Artifact, utc_now_iso
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class ArtifactRepository:
    def __init__(self, session_maker: async_sessionmaker[AsyncSession]):
        self._session_maker = session_maker

    @staticmethod
    def _to_domain(model: ArtifactModel) -> Artifact:
        return Artifact(
            id=model.id,
            profile_id=model.profile_id,
            name=model.name,
            size=model.size,
            kind=model.kind,
            state=model.state,
            content_type=model.content_type,
            picker_name=model.picker_name,
            sha256=model.sha256,
            storage_path=model.storage_path,
            delete_requested_at=model.delete_requested_at,
            created_at=model.created_at,
        )

    async def profile_exists(self, profile_id: str) -> bool:
        """Scalar existence check; never materializes the profile aggregate."""
        async with self._session_maker() as session:
            found = (
                await session.execute(
                    select(ProfileModel.id)
                    .where(ProfileModel.id == profile_id)
                    .limit(1)
                )
            ).scalar()
            return found is not None

    async def list_artifacts(self, profile_id: str) -> list[Artifact]:
        async with self._session_maker() as session:
            rows = (
                (
                    await session.execute(
                        select(ArtifactModel)
                        .where(ArtifactModel.profile_id == profile_id)
                        .order_by(ArtifactModel.created_at.desc())
                    )
                )
                .scalars()
                .all()
            )
            return [self._to_domain(row) for row in rows]

    async def get_artifact(self, profile_id: str, artifact_id: str) -> Artifact | None:
        async with self._session_maker() as session:
            row = await session.get(ArtifactModel, artifact_id)
            if row is None or row.profile_id != profile_id:
                return None
            return self._to_domain(row)

    async def find_download_duplicate(
        self,
        profile_id: str,
        *,
        sha256: str,
        storage_path: str,
    ) -> Artifact | None:
        # The path predicate lives in SQL: checksum history must not be
        # scanned in Python to answer a single duplicate lookup.
        async with self._session_maker() as session:
            row = (
                (
                    await session.execute(
                        select(ArtifactModel).where(
                            ArtifactModel.profile_id == profile_id,
                            ArtifactModel.kind == "download",
                            ArtifactModel.sha256 == sha256,
                            ArtifactModel.storage_path == storage_path,
                        )
                    )
                )
                .scalars()
                .first()
            )
            return self._to_domain(row) if row is not None else None

    async def create_artifact(
        self,
        *,
        profile_id: str,
        artifact_id: str | None = None,
        name: str,
        size: int,
        kind: str,
        state: str,
        content_type: str | None,
        sha256: str | None,
        storage_path: str | None,
    ) -> Artifact:
        row = ArtifactModel(
            id=artifact_id or str(uuid.uuid4()),
            profile_id=profile_id,
            name=name,
            size=size,
            kind=kind,
            state=state,
            content_type=content_type,
            picker_name=None,
            sha256=sha256,
            storage_path=storage_path,
            created_at=utc_now_iso(),
        )
        async with self._session_maker() as session, write_transaction(session):
            session.add(row)
        return self._to_domain(row)

    async def delete_artifact(self, profile_id: str, artifact_id: str) -> bool:
        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(ArtifactModel, artifact_id)
            if row is None or row.profile_id != profile_id:
                return False
            await session.delete(row)
            return True

    async def mark_delete_requested(
        self, profile_id: str, artifact_id: str
    ) -> Artifact | None:
        """Persist the deletion intent before any file is touched.

        Re-marking an already-marked artifact keeps the original timestamp
        so retries and restarts observe one durable intent.
        """
        async with self._session_maker() as session, write_transaction(session):
            row = await session.get(ArtifactModel, artifact_id)
            if row is None or row.profile_id != profile_id:
                return None
            if row.delete_requested_at is None:
                row.delete_requested_at = utc_now_iso()
            return self._to_domain(row)

    async def list_pending_deletions(self) -> list[Artifact]:
        async with self._session_maker() as session:
            rows = (
                (
                    await session.execute(
                        select(ArtifactModel).where(
                            ArtifactModel.delete_requested_at.is_not(None)
                        )
                    )
                )
                .scalars()
                .all()
            )
            return [self._to_domain(row) for row in rows]

    async def is_trusted_instance(
        self, profile_id: str, runtime_instance_id: str
    ) -> bool:
        """Whether *runtime_instance_id* is a known instance of the profile.

        Trusted means currently bound or present in the profile's recorded
        runtime history; a late download report from such an instance is
        legitimate, while an unknown/forged instance id is not.
        """
        async with self._session_maker() as session:
            current = (
                await session.execute(
                    select(ProfileRuntimeModel.runtime_instance_id).where(
                        ProfileRuntimeModel.profile_id == profile_id,
                        ProfileRuntimeModel.runtime_instance_id
                        == runtime_instance_id,
                    )
                )
            ).scalar()
            if current is not None:
                return True
            historical = (
                await session.execute(
                    select(RuntimeEventModel.event_id)
                    .where(
                        RuntimeEventModel.profile_id == profile_id,
                        RuntimeEventModel.runtime_instance_id
                        == runtime_instance_id,
                    )
                    .limit(1)
                )
            ).scalar()
            return historical is not None

    async def delete_profile_artifacts(self, profile_id: str) -> None:
        async with self._session_maker() as session, write_transaction(session):
            await session.execute(
                delete(ArtifactModel).where(ArtifactModel.profile_id == profile_id)
            )
