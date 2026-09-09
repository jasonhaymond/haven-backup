import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, scheduler
from app.db import init_db
from app.routers import auth, credentials, dashboard, hosts, repos, runs


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if os.environ.get("HAVEN_DISABLE_SCHEDULER") != "1":
        scheduler.start()
    yield
    if os.environ.get("HAVEN_DISABLE_SCHEDULER") != "1":
        scheduler.shutdown()


app = FastAPI(title="Haven Backup Portal", lifespan=lifespan)

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


@app.get("/api/health")
def health():
    return {"status": "ok"}
