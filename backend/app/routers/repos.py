from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import crypto, repo_service
from app.db import get_session
from app.deps import get_current_user
from app.models import CheckRun, PruneRun, Repo, RepoStatusSnapshot

router = APIRouter(prefix="/api/repos", tags=["repos"], dependencies=[Depends(get_current_user)])


class RepoIn(BaseModel):
    name: str
    repo_url: str
    ssh_credential_id: int
    passphrase: str
    client_host_id: Optional[int] = None
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    keep_yearly: int = 1
    expected_interval_hours: int = 26
    notes: str = ""


class RepoOut(BaseModel):
    id: int
    name: str
    repo_url: str
    ssh_credential_id: int
    client_host_id: Optional[int]
    keep_daily: int
    keep_weekly: int
    keep_monthly: int
    keep_yearly: int
    expected_interval_hours: int
    notes: str


def _to_out(repo: Repo) -> RepoOut:
    return RepoOut(**{k: getattr(repo, k) for k in RepoOut.model_fields})


@router.get("", response_model=list[RepoOut])
def list_repos(session: Session = Depends(get_session)):
    return [_to_out(r) for r in session.exec(select(Repo)).all()]


@router.post("", response_model=RepoOut)
def create_repo(body: RepoIn, session: Session = Depends(get_session)):
    if session.exec(select(Repo).where(Repo.name == body.name)).first():
        raise HTTPException(status_code=409, detail="A repo with this name already exists")

    data = body.model_dump(exclude={"passphrase"})
    repo = Repo(**data, passphrase_encrypted=crypto.encrypt(body.passphrase))
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return _to_out(repo)


@router.put("/{repo_id}", response_model=RepoOut)
def update_repo(repo_id: int, body: RepoIn, session: Session = Depends(get_session)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    for field, value in body.model_dump(exclude={"passphrase"}).items():
        setattr(repo, field, value)
    if body.passphrase:
        repo.passphrase_encrypted = crypto.encrypt(body.passphrase)

    session.add(repo)
    session.commit()
    session.refresh(repo)
    return _to_out(repo)


@router.delete("/{repo_id}")
def delete_repo(repo_id: int, session: Session = Depends(get_session)):
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    session.delete(repo)
    session.commit()
    return {"ok": True}


def _get_repo_or_404(session: Session, repo_id: int) -> Repo:
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")
    return repo


class SnapshotOut(BaseModel):
    id: int
    repo_id: int
    captured_at: datetime
    ok: bool
    error: Optional[str]
    num_archives: Optional[int]
    original_size: Optional[int]
    compressed_size: Optional[int]
    deduplicated_size: Optional[int]
    last_archive_name: Optional[str]
    last_archive_time: Optional[datetime]
    is_stale: bool


def _with_staleness(snapshot: RepoStatusSnapshot, repo: Repo) -> SnapshotOut:
    stale = False
    if snapshot.ok and snapshot.last_archive_time:
        age_hours = (datetime.now(timezone.utc) - snapshot.last_archive_time.replace(tzinfo=timezone.utc)).total_seconds() / 3600
        stale = age_hours > repo.expected_interval_hours
    elif not snapshot.ok:
        stale = True
    return SnapshotOut(**snapshot.model_dump(), is_stale=stale)


@router.post("/{repo_id}/refresh", response_model=SnapshotOut)
def refresh_repo(repo_id: int, session: Session = Depends(get_session)):
    repo = _get_repo_or_404(session, repo_id)
    snapshot = repo_service.refresh_status(session, repo)
    return _with_staleness(snapshot, repo)


@router.get("/{repo_id}/status", response_model=Optional[SnapshotOut])
def latest_status(repo_id: int, session: Session = Depends(get_session)):
    repo = _get_repo_or_404(session, repo_id)
    snapshot = session.exec(
        select(RepoStatusSnapshot).where(RepoStatusSnapshot.repo_id == repo_id).order_by(RepoStatusSnapshot.captured_at.desc())
    ).first()
    return _with_staleness(snapshot, repo) if snapshot else None


@router.get("/{repo_id}/history", response_model=list[SnapshotOut])
def history(repo_id: int, limit: int = 100, session: Session = Depends(get_session)):
    repo = _get_repo_or_404(session, repo_id)
    snapshots = session.exec(
        select(RepoStatusSnapshot)
        .where(RepoStatusSnapshot.repo_id == repo_id)
        .order_by(RepoStatusSnapshot.captured_at.desc())
        .limit(limit)
    ).all()
    return [_with_staleness(s, repo) for s in snapshots]


class PruneRunOut(BaseModel):
    id: int
    repo_id: int
    dry_run: bool
    status: str
    archives_deleted: int
    output_log: str
    started_at: datetime
    finished_at: Optional[datetime]


@router.post("/{repo_id}/prune", response_model=PruneRunOut)
def prune_repo(repo_id: int, background_tasks: BackgroundTasks, dry_run: bool = True, session: Session = Depends(get_session)):
    repo = _get_repo_or_404(session, repo_id)
    run = repo_service.create_pending_prune(session, repo, dry_run, triggered_by="manual")
    background_tasks.add_task(_run_prune_background, run.id, repo_id)
    return run


def _run_prune_background(run_id: int, repo_id: int):
    from sqlmodel import Session as _Session

    from app.db import engine

    with _Session(engine) as session:
        repo = session.get(Repo, repo_id)
        run = session.get(PruneRun, run_id)
        repo_service.execute_prune(session, run, repo)


class CheckRunOut(BaseModel):
    id: int
    repo_id: int
    status: str
    output_log: str
    started_at: datetime
    finished_at: Optional[datetime]


@router.post("/{repo_id}/check", response_model=CheckRunOut)
def check_repo(repo_id: int, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    repo = _get_repo_or_404(session, repo_id)
    run = repo_service.create_pending_check(session, repo, triggered_by="manual")
    background_tasks.add_task(_run_check_background, run.id, repo_id)
    return run


def _run_check_background(run_id: int, repo_id: int):
    from sqlmodel import Session as _Session

    from app.db import engine

    with _Session(engine) as session:
        repo = session.get(Repo, repo_id)
        run = session.get(CheckRun, run_id)
        repo_service.execute_check(session, run, repo)
