"""Application factory: wires together config, database, routes and scheduler."""

from __future__ import annotations

import atexit
import logging

from flask import Flask

from .api import bp
from .config import Settings, load_targets, settings as default_settings
from .database import Database

logger = logging.getLogger(__name__)


def _configure_logging(debug: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )


def sync_targets_from_config(db: Database, settings: Settings) -> None:
    """Load YAML target definitions into the database (idempotent upsert)."""
    specs = load_targets(settings.config_file)
    for spec in specs:
        db.upsert_target(spec.as_row())
    if specs:
        logger.info("Synced %d target(s) from %s", len(specs), settings.config_file)


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or default_settings
    _configure_logging(settings.debug)

    app = Flask(__name__)
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["SETTINGS"] = settings

    db = Database(settings.db_file)
    db.init_db()
    app.config["DB"] = db

    sync_targets_from_config(db, settings)
    app.register_blueprint(bp)

    if settings.enable_scheduler:
        # Avoid double-starting under the Flask reloader's parent process.
        import os

        if not settings.debug or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
            from .scheduler import ProbeScheduler

            scheduler = ProbeScheduler(db, settings)
            scheduler.start()
            app.config["SCHEDULER"] = scheduler
            atexit.register(scheduler.shutdown)

    return app
