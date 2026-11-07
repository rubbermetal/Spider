"""Dashboard page, JSON stats endpoint and crawl control buttons."""

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, url_for
from spiderlib import db, crawler
from spiderlib.admin.dbconn import get_conn
from datetime import datetime, timedelta, timezone

bp = Blueprint("dashboard", __name__)

def snapshot(conn, running: bool) -> dict:
    stats = db.get_stats(conn)
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    pages_per_min = round(db.count_fetched_since(conn, cutoff) / 5, 1)
    return {
        "running": running,
        "pages_per_min": pages_per_min,
        "queued": stats["by_status"].get("queued", 0),
        "fetching": stats["by_status"].get("fetching", 0),
        "done": stats["by_status"].get("done", 0),
        "errors": stats["by_status"].get("error", 0),
        **stats
    }

def runner():
    return current_app.extensions["spider_runner"]

@bp.route("/", methods=["GET"])
def index():
    conn = get_conn()
    data = snapshot(conn, runner().is_running())
    recent = db.get_recent_logs(conn, 10)
    return render_template("dashboard.html", s=data, recent=recent)

@bp.route("/api/stats", methods=["GET"])
def stats():
    return jsonify(snapshot(get_conn(), runner().is_running()))

@bp.route("/control/<action>", methods=["POST"])
def control(action):
    conn = get_conn()
    if action == "start":
        forever = request.form.get("forever") == "yes"
        ok = runner().start(current_app.config["DB_PATH"], exit_when_idle=not forever)
        detail = ("started (keep running)" if forever else "started") if ok else "already running"
    elif action == "pause":
        crawler.pause(conn)
        detail = ""
    elif action == "resume":
        crawler.resume(conn)
        detail = ""
    elif action == "stop":
        crawler.request_stop(conn)
        detail = ""
    else:
        return "unknown action", 404

    db.audit(conn, "admin", action, detail)
    return redirect(url_for("dashboard.index"))
