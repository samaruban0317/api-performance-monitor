"""Background scheduler that probes each enabled target on its own interval."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from .config import Settings
from .database import Database
from .monitor import probe_and_store

logger = logging.getLogger(__name__)


class ProbeScheduler:
    """Wraps APScheduler to keep one job per enabled target in sync with the DB."""

    def __init__(self, db: Database, settings: Settings) -> None:
        self.db = db
        self.settings = settings
        self.scheduler = BackgroundScheduler(
            timezone="UTC",
            job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 30},
        )

    def start(self) -> None:
        self.sync_jobs()
        self.scheduler.add_job(
            self.sync_jobs,
            trigger="interval",
            seconds=60,
            id="__sync_jobs__",
            replace_existing=True,
        )
        self.scheduler.add_job(
            self._prune,
            trigger="interval",
            hours=1,
            id="__prune__",
            replace_existing=True,
        )
        self.scheduler.start()
        logger.info("Probe scheduler started")

    def shutdown(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)
            logger.info("Probe scheduler stopped")

    def sync_jobs(self) -> None:
        """Reconcile scheduler jobs with the current set of enabled targets.

        New targets get a job that fires immediately; removed/disabled targets
        have their jobs deleted; existing jobs keep their schedule unless the
        configured interval changed.
        """
        targets = {
            t["id"]: t for t in self.db.list_targets(include_disabled=False)
        }
        existing = {
            job.id: job
            for job in self.scheduler.get_jobs()
            if not job.id.startswith("__")
        }
        desired = {f"target-{tid}" for tid in targets}

        for stale in set(existing) - desired:
            self.scheduler.remove_job(stale)
            logger.info("Removed probe job %s", stale)

        for tid, target in targets.items():
            job_id = f"target-{tid}"
            interval = int(target["interval_seconds"])
            job = existing.get(job_id)

            if job is None:
                self.scheduler.add_job(
                    probe_and_store,
                    trigger=IntervalTrigger(seconds=interval),
                    args=[self.db, target],
                    id=job_id,
                    next_run_time=datetime.now(timezone.utc),
                )
                logger.info("Scheduled probe job %s every %ss", target["name"], interval)
                continue

            # Refresh args (URL/headers may have changed) and reschedule only
            # when the interval actually differs, so we don't reset timers.
            job.modify(args=[self.db, target])
            current_interval = getattr(job.trigger, "interval", None)
            if current_interval and current_interval.total_seconds() != interval:
                job.reschedule(trigger=IntervalTrigger(seconds=interval))
                logger.info("Rescheduled %s to every %ss", target["name"], interval)

    def _prune(self) -> None:
        deleted = self.db.prune(self.settings.retention_days)
        if deleted:
            logger.info("Pruned %d expired metric samples", deleted)
