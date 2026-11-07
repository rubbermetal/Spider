"""Domains admin page: per-host stats, block/unblock, delay override, notes, robots.txt viewer."""

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from spiderlib import db, robots
from spiderlib.admin import domains_ops, domains_queries
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("domains", __name__)

@bp.route("/domains", methods=["GET"])
def index():
    f = domains_queries.parse_args(request.args)
    rows, pg = domains_queries.list_domains(get_conn(), f)
    return render_template("domains.html", rows=rows, pg=pg, f=f, qs=domains_queries.query_dict(f), sorts=domains_queries.SORTS, per_page_choices=domains_queries.PER_PAGE_CHOICES)

@bp.route("/domains/block", methods=["POST"])
def block_new():
    ok = domains_ops.set_blocked(get_conn(), request.form.get("host", ""), True)
    flash("Domain blocked." if ok else "Not a valid host name.")
    return redirect(url_for("domains.index"))

@bp.route("/domains/<host>", methods=["GET"])
def detail(host):
    d = domains_queries.get_domain(get_conn(), host.lower())
    if d is None:
        abort(404)
    return render_template("domain_detail.html", d=d, recent=domains_queries.recent_urls(get_conn(), d["host"]), settings=db.get_settings(get_conn()))

@bp.route("/domains/<host>/block", methods=["POST"])
def block(host):
    conn = get_conn()
    if not domains_ops.set_blocked(conn, host, True):
        abort(404)
    flash("Domain blocked.")
    return redirect(url_for("domains.detail", host=host))

@bp.route("/domains/<host>/unblock", methods=["POST"])
def unblock(host):
    conn = get_conn()
    if not domains_ops.set_blocked(conn, host, False):
        abort(404)
    flash("Domain unblocked.")
    return redirect(url_for("domains.detail", host=host))

@bp.route("/domains/<host>/delay", methods=["POST"])
def delay(host):
    conn = get_conn()
    err = domains_ops.set_delay(conn, host, request.form.get("delay", ""))
    flash(err if err else "Delay saved.")
    return redirect(url_for("domains.detail", host=host))

@bp.route("/domains/<host>/notes", methods=["POST"])
def notes(host):
    conn = get_conn()
    err = domains_ops.set_notes(conn, host, request.form.get("notes", ""))
    flash(err if err else "Notes saved.")
    return redirect(url_for("domains.detail", host=host))

@bp.route("/domains/<host>/robots", methods=["POST"])
def robots_refetch(host):
    conn = get_conn()
    fetcher = current_app.config.get("ROBOTS_FETCHER", robots.fetch_robots_txt)
    status, err = domains_ops.refetch_robots(conn, host, db.get_settings(conn), fetcher)
    flash(err if err else f"robots.txt refetched (status {status}).")
    return redirect(url_for("domains.detail", host=host))
