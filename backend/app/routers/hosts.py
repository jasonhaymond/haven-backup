from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import host_service
from app.db import get_session
from app.deps import get_current_user
from app.models import BackupRun, ClientHost, Repo

router = APIRouter(prefix="/api/hosts", tags=["hosts"], dependencies=[Depends(get_current_user)])


class HostIn(BaseModel):
    name: str
    ssh_credential_id: int
    borgmatic_config_path: str = "/etc/borgmatic/config.yaml"
    notes: str = ""


class HostOut(BaseModel):
    id: int
    name: str
    ssh_credential_id: int
    borgmatic_config_path: str
    notes: str


@router.get("", response_model=list[HostOut])
def list_hosts(session: Session = Depends(get_session)):
    return session.exec(select(ClientHost)).all()


@router.post("", response_model=HostOut)
def create_host(body: HostIn, session: Session = Depends(get_session)):
    if session.exec(select(ClientHost).where(ClientHost.name == body.name)).first():
        raise HTTPException(status_code=409, detail="A host with this name already exists")
    host = ClientHost(**body.model_dump())
    session.add(host)
    session.commit()
    session.refresh(host)
    return host


@router.delete("/{host_id}")
def delete_host(host_id: int, session: Session = Depends(get_session)):
    host = session.get(ClientHost, host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    session.delete(host)
    session.commit()
    return {"ok": True}


class BackupRunOut(BaseModel):
    id: int
    repo_id: int
    host_id: int | None
    status: str
    triggered_by: str


@router.post("/{host_id}/backup-now", response_model=BackupRunOut)
def backup_now(host_id: int, repo_id: int, background_tasks: BackgroundTasks, session: Session = Depends(get_session)):
    host = session.get(ClientHost, host_id)
    if host is None:
        raise HTTPException(status_code=404, detail="Host not found")
    repo = session.get(Repo, repo_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repo not found")

    # Create the "running" row synchronously so the caller gets an id to poll immediately;
    # the actual SSH exec + borgmatic run happens in the background (can take a long time).
    run = host_service.create_pending_run(session, host, repo_id, triggered_by="manual")
    background_tasks.add_task(_run_backup_background, run.id, host_id)
    return run


def _run_backup_background(run_id: int, host_id: int):
    from sqlmodel import Session as _Session

    from app.db import engine
    from app.models import BackupRun as _BackupRun

    with _Session(engine) as session:
        host = session.get(ClientHost, host_id)
        run = session.get(_BackupRun, run_id)
        host_service.execute_run(session, run, host)
