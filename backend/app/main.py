import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from app import __version__, config, scheduler
from app.db import engine, init_db
from app.models import User
from app.routers import auth, credentials, dashboard, hosts, repos, runs, version
from app.version_stamp import stamp_current_version

logging.basicConfig(
    level=os.environ.get("HAVEN_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    with Session(engine) as session:
        stamp_current_version(session)
    if os.environ.get("HAVEN_DISABLE_SCHEDULER") != "1":
        scheduler.start()
    yield
    if os.environ.get("HAVEN_DISABLE_SCHEDULER") != "1":
        scheduler.shutdown()


app = FastAPI(title="Haven Backup Portal", version=__version__, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[config.FRONTEND_ORIGIN],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(credentials.router)
app.include_router(hosts.router)
app.include_router(repos.router)
app.include_router(runs.router)
app.include_router(dashboard.router)
app.include_router(version.router)


@app.get("/api/health")
def health():
    """Unauthenticated on purpose -- external uptime monitors need to reach this
    without credentials. Actually exercises the DB, not just "the process is up"."""
    try:
        with Session(engine) as session:
            session.exec(select(User).limit(1)).first()
        db_ok = True
    except Exception:
        db_ok = False

    return {"status": "ok" if db_ok else "degraded", "version": __version__, "database": db_ok}
