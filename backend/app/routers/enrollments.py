from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import update
from sqlmodel import Session, select

from app import config, crypto
from app import enrollment as enr
from app.db import get_session
from app.deps import get_current_user
from app.models import ClientHost, Enrollment, Repo, SSHCredential
from app.rate_limit import rate_limit

router = APIRouter(tags=["enrollments"])

INSTALL_SCRIPT = Path(__file__).resolve().parent.parent / "static" / "client-install.sh"


def _utc(dt: Optional[datetime]) -> Optional[datetime]:
    # SQLite hands datetimes back naive; they were stored as UTC.
    return dt.replace(tzinfo=timezone.utc) if dt and dt.tzinfo is None else dt


def _credential_name(name: str) -> str:
    return f"{name}-portal-access"


def _names_taken(session: Session, name: str) -> Optional[str]:
    if session.exec(select(ClientHost).where(ClientHost.name == name)).first():
        return "A client host with this name already exists"
    if session.exec(select(Repo).where(Repo.name == name)).first():
        return "A repo with this name already exists"
    if session.exec(select(SSHCredential).where(SSHCredential.name == _credential_name(name))).first():
        return f"An SSH credential named {_credential_name(name)} already exists"
    return None


class EnrollmentIn(BaseModel):
    name: str
    address: str
    ssh_port: int = 22
    backup_credential_id: int
    repo_base_path: str
    source_directories: list[str]
    schedule: str = "*-*-* 02:00:00"
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    keep_yearly: int = 1
    expected_interval_hours: int = 26


class EnrollmentOut(BaseModel):
    id: int
    name: str
    address: str
    ssh_port: int
    backup_credential_id: int
    repo_url: str
    source_directories: list[str]
    schedule: str
    status: str  # pending | expired | claimed
    created_at: datetime
    expires_at: datetime
    claimed_at: Optional[datetime]
    claimed_hostname: Optional[str]
    host_id: Optional[int]
    repo_id: Optional[int]
    backup_server_line: Optional[str]
    backup_server_account: str


class EnrollmentCreated(EnrollmentOut):
    token: str  # shown exactly once


def _to_out(session: Session, e: Enrollment) -> EnrollmentOut:
    cred = session.get(SSHCredential, e.backup_credential_id)
    username, hostname, port = (cred.username, cred.hostname, cred.port) if cred else ("?", "?", 22)
    if e.claimed_at:
        status = "claimed"
    elif _utc(e.expires_at) < datetime.now(timezone.utc):
        status = "expired"
    else:
        status = "pending"
    return EnrollmentOut(
        id=e.id,
        name=e.name,
        address=e.address,
        ssh_port=e.ssh_port,
        backup_credential_id=e.backup_credential_id,
        repo_url=enr.repo_url(username, hostname, port, e.repo_base_path, e.name),
        source_directories=e.source_directories.splitlines(),
        schedule=e.schedule,
        status=status,
        created_at=_utc(e.created_at),
        expires_at=_utc(e.expires_at),
        claimed_at=_utc(e.claimed_at),
        claimed_hostname=e.claimed_hostname,
        host_id=e.host_id,
        repo_id=e.repo_id,
        backup_server_line=(
            enr.backup_server_authorized_keys_line(e.client_public_key, e.repo_base_path, e.name, e.claimed_hostname)
            if e.client_public_key
            else None
        ),
        backup_server_account=f"{username}@{hostname}",
    )


@router.get("/api/enrollments", response_model=list[EnrollmentOut], dependencies=[Depends(get_current_user)])
def list_enrollments(session: Session = Depends(get_session)):
    rows = session.exec(select(Enrollment).order_by(Enrollment.created_at.desc())).all()
    return [_to_out(session, e) for e in rows]


@router.post("/api/enrollments", response_model=EnrollmentCreated, dependencies=[Depends(get_current_user)])
def create_enrollment(body: EnrollmentIn, session: Session = Depends(get_session)):
    try:
        name = enr.validate_name(body.name)
        address = enr.validate_hostname(body.address)
        base_path = enr.validate_abs_path(body.repo_base_path, "Repo base path")
        sources = [enr.validate_abs_path(s, "Source directory") for s in body.source_directories if s.strip()]
        schedule = enr.validate_schedule(body.schedule)
    except enr.EnrollmentError as e:
        raise HTTPException(status_code=422, detail=str(e))
    if not sources:
        raise HTTPException(status_code=422, detail="At least one source directory is required")
    if not 1 <= body.ssh_port <= 65535:
        raise HTTPException(status_code=422, detail="Invalid SSH port")
    if session.get(SSHCredential, body.backup_credential_id) is None:
        raise HTTPException(status_code=422, detail="Backup server credential not found")
    if conflict := _names_taken(session, name):
        raise HTTPException(status_code=409, detail=conflict)
    pending = session.exec(select(Enrollment).where(Enrollment.name == name, Enrollment.claimed_at.is_(None))).all()
    if any(_utc(p.expires_at) > datetime.now(timezone.utc) for p in pending):
        raise HTTPException(status_code=409, detail="An unexpired enrollment with this name already exists -- revoke it first")

    token = enr.new_token()
    private_pem, public_line = enr.generate_keypair(f"haven-backup-portal@{name}")
    row = Enrollment(
        name=name,
        token_hash=enr.hash_token(token),
        address=address,
        ssh_port=body.ssh_port,
        backup_credential_id=body.backup_credential_id,
        repo_base_path=base_path,
        source_directories="\n".join(sources),
        schedule=schedule,
        keep_daily=body.keep_daily,
        keep_weekly=body.keep_weekly,
        keep_monthly=body.keep_monthly,
        keep_yearly=body.keep_yearly,
        expected_interval_hours=body.expected_interval_hours,
        passphrase_encrypted=crypto.encrypt(enr.new_passphrase()),
        portal_private_key_encrypted=crypto.encrypt(private_pem),
        portal_public_key=public_line,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=config.ENROLLMENT_TOKEN_TTL_MINUTES),
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return EnrollmentCreated(**_to_out(session, row).model_dump(), token=token)


@router.delete("/api/enrollments/{enrollment_id}", dependencies=[Depends(get_current_user)])
def delete_enrollment(enrollment_id: int, session: Session = Depends(get_session)):
    """Revokes an unclaimed enrollment. For a claimed one this only removes the record --
    the host/repo/credential it created stay, and are deleted from their own pages."""
    row = session.get(Enrollment, enrollment_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    session.delete(row)
    session.commit()
    return {"ok": True}


# -----------------------------
# Unauthenticated: called by the install script on the client
# -----------------------------
@router.get("/api/enroll/install.sh", response_class=PlainTextResponse)
def install_script():
    return PlainTextResponse(INSTALL_SCRIPT.read_text(encoding="utf-8"), media_type="text/x-shellscript")


class ClaimIn(BaseModel):
    token: str
    hostname: str
    client_public_key: str
    borgmatic_version: str
    borgmatic_path: str


class ClaimOut(BaseModel):
    name: str
    repo_url: str
    passphrase: str
    borgmatic_config: str
    borgmatic_config_path: str
    systemd_service: str
    systemd_timer: str
    systemd_unit_name: str
    portal_authorized_keys_line: str
    backup_server_line: str
    backup_server_account: str
    client_key_path: str


@router.post(
    "/api/enroll/claim",
    response_model=ClaimOut,
    dependencies=[rate_limit(config.LOGIN_RATE_LIMIT_ATTEMPTS, config.LOGIN_RATE_LIMIT_WINDOW_SECONDS)],
)
def claim(body: ClaimIn, session: Session = Depends(get_session)):
    row = session.exec(select(Enrollment).where(Enrollment.token_hash == enr.hash_token(body.token))).first()
    # One message for unknown/used/expired, so the endpoint doesn't confirm which tokens exist.
    gone = HTTPException(status_code=410, detail="This install command is invalid, expired, or already used -- generate a new one in the portal")
    if row is None or row.claimed_at is not None or _utc(row.expires_at) < datetime.now(timezone.utc):
        raise gone

    try:
        hostname = enr.validate_hostname(body.hostname)
        client_key = enr.normalize_public_key(body.client_public_key)
        borgmatic_path = enr.validate_abs_path(body.borgmatic_path, "borgmatic path")
    except enr.EnrollmentError as e:
        raise HTTPException(status_code=422, detail=str(e))

    cred = session.get(SSHCredential, row.backup_credential_id)
    if cred is None:
        raise HTTPException(status_code=409, detail="The backup server credential this enrollment used has been deleted")
    if conflict := _names_taken(session, row.name):
        raise HTTPException(status_code=409, detail=conflict)

    # Conditional update so two concurrent claims of the same token can't both win.
    result = session.exec(
        update(Enrollment)
        .where(Enrollment.id == row.id, Enrollment.claimed_at.is_(None))
        .values(claimed_at=datetime.now(timezone.utc), claimed_hostname=hostname, client_public_key=client_key)
    )
    if result.rowcount != 1:
        session.rollback()
        raise gone

    passphrase = crypto.decrypt(row.passphrase_encrypted)
    url = enr.repo_url(cred.username, cred.hostname, cred.port, row.repo_base_path, row.name)

    portal_cred = SSHCredential(
        name=_credential_name(row.name),
        hostname=row.address,
        port=row.ssh_port,
        username="root",
        private_key_encrypted=row.portal_private_key_encrypted,
    )
    session.add(portal_cred)
    session.flush()
    host = ClientHost(
        name=row.name,
        ssh_credential_id=portal_cred.id,
        borgmatic_config_path=enr.CLIENT_CONFIG_PATH,
        notes=f"Enrolled via one-line install from {hostname}",
    )
    session.add(host)
    session.flush()
    repo = Repo(
        name=row.name,
        repo_url=url,
        ssh_credential_id=cred.id,
        passphrase_encrypted=row.passphrase_encrypted,
        client_host_id=host.id,
        keep_daily=row.keep_daily,
        keep_weekly=row.keep_weekly,
        keep_monthly=row.keep_monthly,
        keep_yearly=row.keep_yearly,
        expected_interval_hours=row.expected_interval_hours,
    )
    session.add(repo)
    session.flush()
    session.refresh(row)
    row.host_id, row.repo_id = host.id, repo.id
    session.add(row)
    session.commit()

    return ClaimOut(
        name=row.name,
        repo_url=url,
        passphrase=passphrase,
        borgmatic_config=enr.render_borgmatic_config(
            body.borgmatic_version, row.name, url, passphrase, row.source_directories.splitlines()
        ),
        borgmatic_config_path=enr.CLIENT_CONFIG_PATH,
        systemd_service=enr.render_systemd_service(row.name, borgmatic_path),
        systemd_timer=enr.render_systemd_timer(row.name, row.schedule),
        systemd_unit_name=enr.SYSTEMD_UNIT_NAME,
        portal_authorized_keys_line=enr.portal_authorized_keys_line(row.portal_public_key, borgmatic_path),
        backup_server_line=enr.backup_server_authorized_keys_line(client_key, row.repo_base_path, row.name, hostname),
        backup_server_account=f"{cred.username}@{cred.hostname}",
        client_key_path=enr.CLIENT_BORG_KEY_PATH,
    )
