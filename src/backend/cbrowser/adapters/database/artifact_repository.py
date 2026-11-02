"""SQLite repository for Artifact metadata; the API is the only writer."""

from __future__ import annotations

import uuid

from cbrowser.adapters.database.models import ArtifactModel, ProfileModel
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
            created_at=model.created_at,
        )

    async def get_profile(self, profile_id: str):
        async with self._session_maker() as session:
            return await session.get(ProfileModel, profile_id)

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
        async with self._session_maker() as session:
            rows = (
                (
                    await session.execute(
                        select(ArtifactModel).where(
                            ArtifactModel.profile_id == profile_id,
                            ArtifactModel.kind == "download",
                            ArtifactModel.sha256 == sha256,
                        )
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                if row.storage_path == storage_path:
                    return self._to_domain(row)
            return None

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

    async def delete_profile_artifacts(self, profile_id: str) -> None:
        async with self._session_maker() as session, write_transaction(session):
            await session.execute(
                delete(ArtifactModel).where(ArtifactModel.profile_id == profile_id)
            )
