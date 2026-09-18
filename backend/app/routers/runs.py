from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app.db import get_session
from app.deps import get_current_user
from app.models import BackupRun, CheckRun, PruneRun

router = APIRouter(prefix="/api/runs", tags=["runs"], dependencies=[Depends(get_current_user)])


class BackupRunOut(BaseModel):
    id: int
    repo_id: int
    host_id: Optional[int]
    triggered_by: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    output_log: str


class PruneRunOut(BaseModel):
    id: int
    repo_id: int
    dry_run: bool
    triggered_by: str
    status: str
    archives_deleted: int
    started_at: datetime
    finished_at: Optional[datetime]
    output_log: str


class CheckRunOut(BaseModel):
    id: int
    repo_id: int
    triggered_by: str
    status: str
    started_at: datetime
    finished_at: Optional[datetime]
    output_log: str


@router.get("/backups", response_model=list[BackupRunOut])
def list_backup_runs(repo_id: Optional[int] = None, host_id: Optional[int] = None, limit: int = 50, session: Session = Depends(get_session)):
    query = select(BackupRun)
    if repo_id is not None:
        query = query.where(BackupRun.repo_id == repo_id)
    if host_id is not None:
        query = query.where(BackupRun.host_id == host_id)
    query = query.order_by(BackupRun.started_at.desc()).limit(limit)
    return session.exec(query).all()


@router.get("/backups/{run_id}", response_model=BackupRunOut)
def get_backup_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(BackupRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/prunes", response_model=list[PruneRunOut])
def list_prune_runs(repo_id: Optional[int] = None, limit: int = 50, session: Session = Depends(get_session)):
    query = select(PruneRun)
    if repo_id is not None:
        query = query.where(PruneRun.repo_id == repo_id)
    query = query.order_by(PruneRun.started_at.desc()).limit(limit)
    return session.exec(query).all()


@router.get("/prunes/{run_id}", response_model=PruneRunOut)
def get_prune_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(PruneRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/checks", response_model=list[CheckRunOut])
def list_check_runs(repo_id: Optional[int] = None, limit: int = 50, session: Session = Depends(get_session)):
    query = select(CheckRun)
    if repo_id is not None:
        query = query.where(CheckRun.repo_id == repo_id)
    query = query.order_by(CheckRun.started_at.desc()).limit(limit)
    return session.exec(query).all()


@router.get("/checks/{run_id}", response_model=CheckRunOut)
def get_check_run(run_id: int, session: Session = Depends(get_session)):
    run = session.get(CheckRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
