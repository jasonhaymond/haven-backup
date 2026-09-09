from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_user
from app.models import ClientHost, Repo, RepoStatusSnapshot

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"], dependencies=[Depends(get_current_user)])


class RepoSummary(BaseModel):
    repo_id: int
    repo_name: str
    client_host_name: str | None
    ok: bool | None
    is_stale: bool
    last_archive_time: datetime | None
    num_archives: int | None
    deduplicated_size: int | None
    error: str | None


@router.get("", response_model=list[RepoSummary])
def dashboard(session: Session = Depends(get_session)):
    repos = session.exec(select(Repo)).all()
    hosts_by_id = {h.id: h for h in session.exec(select(ClientHost)).all()}

    summaries = []
    for repo in repos:
        snapshot = session.exec(
            select(RepoStatusSnapshot)
            .where(RepoStatusSnapshot.repo_id == repo.id)
            .order_by(RepoStatusSnapshot.captured_at.desc())
        ).first()

        is_stale = False
        if snapshot is None:
            is_stale = True
        elif not snapshot.ok:
            is_stale = True
        elif snapshot.last_archive_time:
            age_hours = (
                datetime.now(timezone.utc) - snapshot.last_archive_time.replace(tzinfo=timezone.utc)
            ).total_seconds() / 3600
            is_stale = age_hours > repo.expected_interval_hours

        host = hosts_by_id.get(repo.client_host_id)
        summaries.append(
            RepoSummary(
                repo_id=repo.id,
                repo_name=repo.name,
                client_host_name=host.name if host else None,
                ok=snapshot.ok if snapshot else None,
                is_stale=is_stale,
                last_archive_time=snapshot.last_archive_time if snapshot else None,
                num_archives=snapshot.num_archives if snapshot else None,
                deduplicated_size=snapshot.deduplicated_size if snapshot else None,
                error=snapshot.error if snapshot else None,
            )
        )
    return summaries
