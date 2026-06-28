"""REST API + dashboard routes."""

from __future__ import annotations

import json

from flask import Blueprint, Response, current_app, jsonify, render_template, request

from .insights import WINDOWS, overview, target_stats
from .metrics import render_prometheus
from .monitor import probe_and_store

bp = Blueprint("api", __name__)


def _db():
    return current_app.config["DB"]


def _settings():
    return current_app.config["SETTINGS"]


# --- dashboard --------------------------------------------------------------


@bp.route("/")
def dashboard() -> str:
    return render_template("dashboard.html")


# --- health -----------------------------------------------------------------


@bp.route("/health")
def health() -> Response:
    return jsonify({"status": "ok", "scheduler": _settings().enable_scheduler})


# --- insights ---------------------------------------------------------------


@bp.route("/api/overview")
def api_overview() -> Response:
    window = request.args.get("window", "24h")
    if window not in WINDOWS:
        return jsonify({"error": f"window must be one of {list(WINDOWS)}"}), 400
    return jsonify(overview(_db(), window))


# --- targets ----------------------------------------------------------------


@bp.route("/api/targets", methods=["GET"])
def list_targets() -> Response:
    return jsonify(_db().list_targets())


@bp.route("/api/targets", methods=["POST"])
def create_target() -> Response:
    payload = request.get_json(silent=True) or {}
    if not payload.get("name") or not payload.get("url"):
        return jsonify({"error": "name and url are required"}), 400

    row = {
        "name": payload["name"],
        "url": payload["url"],
        "method": (payload.get("method") or "GET").upper(),
        "headers": json.dumps(payload.get("headers") or {}),
        "body": payload.get("body"),
        "expected_status": int(payload.get("expected_status", 200)),
        "timeout": float(payload.get("timeout", 10)),
        "interval_seconds": int(payload.get("interval", 60)),
        "enabled": 1 if payload.get("enabled", True) else 0,
    }
    target_id = _db().upsert_target(row)
    return jsonify(_db().get_target(target_id)), 201


@bp.route("/api/targets/<int:target_id>", methods=["GET"])
def get_target(target_id: int) -> Response:
    target = _db().get_target(target_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    window = request.args.get("window", "24h")
    target["stats"] = target_stats(_db(), target_id, window if window in WINDOWS else "24h")
    target["recent"] = _db().recent_metrics(target_id, limit=200)
    return jsonify(target)


@bp.route("/api/targets/<int:target_id>", methods=["DELETE"])
def delete_target(target_id: int) -> Response:
    if not _db().delete_target(target_id):
        return jsonify({"error": "not found"}), 404
    return jsonify({"deleted": target_id})


@bp.route("/api/targets/<int:target_id>/check", methods=["POST"])
def check_now(target_id: int) -> Response:
    """Trigger an immediate, synchronous probe (useful for testing a target)."""
    target = _db().get_target(target_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    result = probe_and_store(_db(), target)
    return jsonify(result.as_metric())


# --- prometheus -------------------------------------------------------------


@bp.route("/metrics")
def prometheus_metrics() -> Response:
    window = request.args.get("window", "1h")
    body, content_type = render_prometheus(_db(), window if window in WINDOWS else "1h")
    return Response(body, content_type=content_type)
