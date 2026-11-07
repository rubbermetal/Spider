"""Errors admin page: failures grouped by kind, with retry for a group or selected URLs."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from spiderlib.admin import errors_logic, errors_ops, errors_queries, urls_actions
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("errors", __name__)

def safe_next(value, default):
    if isinstance(value, str) and value.startswith("/errors") and not value.startswith("//"):
        return value
    return default

@bp.route("/errors")
def index():
    conn = get_conn()
    return render_template("errors.html", 
                           groups=errors_queries.group_counts(conn), 
                           hosts=errors_queries.top_hosts(conn), 
                           total=errors_queries.total_problems(conn))

@bp.route("/errors/<kind>")
def group(kind):
    if not errors_logic.is_valid_kind(kind):
        abort(404)
    text = request.args.get("page", "")
    page = int(text) if text.isdigit() and int(text) >= 1 else 1
    rows, pg = errors_queries.list_group(get_conn(), kind, page)
    return render_template("errors_group.html", 
                           kind=kind, 
                           label=errors_logic.label(kind), 
                           rows=rows, 
                           pg=pg)

@bp.route("/errors/<kind>/retry-all", methods=["POST"])
def retry_all(kind):
    n = errors_ops.retry_group(get_conn(), kind)
    if n is None:
        abort(404)
    flash(f"Requeued {n} URL(s).")
    return redirect(url_for("errors.index"))

@bp.route("/errors/retry", methods=["POST"])
def retry_selected():
    ids = urls_actions.parse_ids(request.form.getlist("ids"))
    nxt = safe_next(request.form.get("next"), url_for("errors.index"))
    count, error = urls_actions.apply_action(get_conn(), "requeue", ids)
    flash(error if error else f"Requeued {count} URL(s).")
    return redirect(nxt)
