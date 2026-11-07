"""Event log and audit log pages, with pruning of old log entries."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from spiderlib.admin import logs_filter, logs_queries
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("logs", __name__)

@bp.route("/logs", methods=["GET"])
def index():
    f = logs_filter.parse_log_args(request.args)
    rows, pg = logs_queries.list_log(get_conn(), f)
    return render_template("logs.html", rows=rows, pg=pg, f=f, qs=logs_filter.query_dict(f), levels=logs_filter.LEVELS, per_page_choices=logs_filter.PER_PAGE_CHOICES)

@bp.route("/logs/prune", methods=["POST"])
def prune():
    text = request.form.get("days", "")
    days = int(text) if text.isdigit() else None
    n = logs_queries.prune_log(get_conn(), days)
    flash("Choose a valid number of days." if n is None else f"Deleted {n} log entries.")
    return redirect(url_for("logs.index"))

@bp.route("/audit", methods=["GET"])
def audit():
    f = logs_filter.parse_audit_args(request.args)
    rows, pg = logs_queries.list_audit(get_conn(), f)
    return render_template("audit.html", rows=rows, pg=pg, f=f, qs=logs_filter.query_dict(f), options=logs_queries.audit_options(get_conn()), per_page_choices=logs_filter.PER_PAGE_CHOICES)
