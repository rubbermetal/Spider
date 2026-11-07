"""URL browser pages and actions: list with filters, detail, single and bulk actions."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from spiderlib.admin import urls_actions, urls_filter, urls_queries
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("urls", __name__)

def safe_next(value, default):
    if isinstance(value, str) and value.startswith("/urls") and not value.startswith("//"):
        return value
    return default

@bp.route("/urls", methods=["GET"])
def index():
    conn = get_conn()
    f = urls_filter.parse_filters(request.args)
    rows, pg = urls_queries.list_urls(conn, f)
    return render_template("urls.html", rows=rows, pg=pg, f=f, qs=urls_filter.query_dict(f),
                           counts=urls_queries.status_counts(conn), seeds=urls_queries.seed_options(conn),
                           statuses=urls_filter.STATUSES, sorts=urls_filter.SORTS,
                           per_page_choices=urls_filter.PER_PAGE_CHOICES, actions=urls_actions.ACTIONS)

@bp.route("/urls/<int:url_id>", methods=["GET"])
def detail(url_id):
    conn = get_conn()
    u = urls_queries.get_url(conn, url_id)
    if u is None:
        abort(404)
    return render_template("url_detail.html", u=u, inbound=urls_queries.inbound_links(conn, url_id),
                           outbound=urls_queries.outbound_links(conn, url_id), actions=urls_actions.ACTIONS)

@bp.route("/urls/action", methods=["POST"])
def bulk():
    action = request.form.get("action", "")
    ids = urls_actions.parse_ids(request.form.getlist("ids"))
    value = request.form.get("value", "")
    nxt = safe_next(request.form.get("next"), url_for("urls.index"))
    if action == "delete" and request.form.get("confirm") != "yes":
        flash("Tick confirm to delete.")
        return redirect(nxt)
    count, error = urls_actions.apply_action(get_conn(), action, ids, value)
    flash(error if error else f"{action}: {count} URL(s).")
    return redirect(nxt)

@bp.route("/urls/<int:url_id>/action", methods=["POST"])
def single(url_id):
    conn = get_conn()
    if urls_queries.get_url(conn, url_id) is None:
        abort(404)
    action = request.form.get("action", "")
    value = request.form.get("value", "")
    if action == "delete" and request.form.get("confirm") != "yes":
        flash("Tick confirm to delete.")
        return redirect(url_for("urls.detail", url_id=url_id))
    count, error = urls_actions.apply_action(conn, action, [url_id], value)
    flash(error if error else f"{action}: {count} URL(s).")
    if action == "delete" and not error:
        return redirect(url_for("urls.index"))
    return redirect(url_for("urls.detail", url_id=url_id))
