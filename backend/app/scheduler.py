"""Background jobs: periodic repo status refresh, scheduled pruning, staleness alerts.

Runs in-process via APScheduler's BackgroundScheduler (a plain thread pool) --
our repo/host service calls are blocking (subprocess/SSH), so there's no
benefit to an asyncio-native scheduler here.
"""

import logging

from apscheduler.schedulers.background import BackgroundScheduler
from sqlmodel import Session, select

from app import config, notifications, repo_service
from app.db import engine
from app.models import Repo

logger = logging.getLogger("haven_backup.scheduler")

_scheduler = BackgroundScheduler()
_last_known_stale: dict[int, bool] = {}


def refresh_all_repos():
    with Session(engine) as session:
        for repo in session.exec(select(Repo)).all():
            try:
                snapshot = repo_service.refresh_status(session, repo)
            except Exception as e:  # a single repo's failure must not kill the scheduled job
                logger.error("Status refresh failed for repo %s: %s", repo.name, e)
                continue

            is_stale = not snapshot.ok
            was_stale = _last_known_stale.get(repo.id, False)
            if is_stale and not was_stale:
                notifications.notify("repo_unhealthy", f"Repo '{repo.name}' failed its status check: {snapshot.error}")
            _last_known_stale[repo.id] = is_stale


def prune_all_repos():
    with Session(engine) as session:
        for repo in session.exec(select(Repo)).all():
            try:
                run = repo_service.run_prune(session, repo, dry_run=False, triggered_by="scheduled")
                if run.status != "success":
                    notifications.notify("prune_failed", f"Scheduled prune failed for repo '{repo.name}'")
            except Exception as e:
                logger.error("Scheduled prune failed for repo %s: %s", repo.name, e)


def start():
    _scheduler.add_job(refresh_all_repos, "interval", minutes=config.STATUS_REFRESH_INTERVAL_MINUTES, id="refresh_all_repos", replace_existing=True)
    _scheduler.add_job(prune_all_repos, "interval", hours=config.PRUNE_INTERVAL_HOURS, id="prune_all_repos", replace_existing=True)
    _scheduler.start()


def shutdown():
    _scheduler.shutdown(wait=False)
