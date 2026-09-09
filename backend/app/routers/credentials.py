from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select

from app import crypto
from app.db import get_session
from app.deps import get_current_user
from app.models import SSHCredential

router = APIRouter(prefix="/api/credentials", tags=["credentials"])


class CredentialIn(BaseModel):
    name: str
    hostname: str
    port: int = 22
    username: str
    private_key: str  # PEM text, encrypted before storage, never returned
    key_passphrase: Optional[str] = None


class CredentialOut(BaseModel):
    id: int
    name: str
    hostname: str
    port: int
    username: str
    has_key_passphrase: bool


def _to_out(cred: SSHCredential) -> CredentialOut:
    return CredentialOut(
        id=cred.id, name=cred.name, hostname=cred.hostname, port=cred.port,
        username=cred.username, has_key_passphrase=cred.key_passphrase_encrypted is not None,
    )


@router.get("", response_model=list[CredentialOut], dependencies=[Depends(get_current_user)])
def list_credentials(session: Session = Depends(get_session)):
    return [_to_out(c) for c in session.exec(select(SSHCredential)).all()]


@router.post("", response_model=CredentialOut, dependencies=[Depends(get_current_user)])
def create_credential(body: CredentialIn, session: Session = Depends(get_session)):
    if session.exec(select(SSHCredential).where(SSHCredential.name == body.name)).first():
        raise HTTPException(status_code=409, detail="A credential with this name already exists")

    cred = SSHCredential(
        name=body.name,
        hostname=body.hostname,
        port=body.port,
        username=body.username,
        private_key_encrypted=crypto.encrypt(body.private_key),
        key_passphrase_encrypted=crypto.encrypt(body.key_passphrase) if body.key_passphrase else None,
    )
    session.add(cred)
    session.commit()
    session.refresh(cred)
    return _to_out(cred)


@router.delete("/{credential_id}", dependencies=[Depends(get_current_user)])
def delete_credential(credential_id: int, session: Session = Depends(get_session)):
    cred = session.get(SSHCredential, credential_id)
    if cred is None:
        raise HTTPException(status_code=404, detail="Credential not found")
    session.delete(cred)
    session.commit()
    return {"ok": True}
