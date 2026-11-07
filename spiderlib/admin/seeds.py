"""Seeds admin page: list, add, edit limits, enable/disable, recrawl, delete."""

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from spiderlib.admin import seeds_ops
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("seeds", __name__)

@bp.route("/seeds", methods=["GET"])
def index():
    conn = get_conn()
    seeds = seeds_ops.list_seeds(conn)
    return render_template("seeds.html", seeds=seeds, errors={}, form={})

@bp.route("/seeds/add", methods=["POST"])
def add():
    conn = get_conn()
    seed_id, errors = seeds_ops.add_from_form(conn, request.form)
    if errors:
        return render_template("seeds.html", seeds=seeds_ops.list_seeds(conn), errors=errors, form=request.form), 400
    flash("Seed added.")
    return redirect(url_for("seeds.index"))

@bp.route("/seeds/<int:seed_id>/edit", methods=["GET", "POST"])
def edit(seed_id):
    conn = get_conn()
    seed = seeds_ops.get_seed(conn, seed_id)
    if seed is None:
        abort(404)
    if request.method == "GET":
        return render_template("seed_edit.html", seed=seed, errors={}, form={})
    ok, errors = seeds_ops.update_from_form(conn, seed_id, request.form)
    if not ok:
        return render_template("seed_edit.html", seed=seed, errors=errors, form=request.form), 400
    flash("Seed updated.")
    return redirect(url_for("seeds.index"))

@bp.route("/seeds/<int:seed_id>/toggle", methods=["POST"])
def toggle(seed_id):
    conn = get_conn()
    seed = seeds_ops.get_seed(conn, seed_id)
    if seed is None:
        abort(404)
    seeds_ops.set_enabled(conn, seed_id, not seed["enabled"])
    flash("Seed disabled." if seed["enabled"] else "Seed enabled.")
    return redirect(url_for("seeds.index"))

@bp.route("/seeds/<int:seed_id>/recrawl", methods=["POST"])
def recrawl(seed_id):
    conn = get_conn()
    n = seeds_ops.recrawl(conn, seed_id)
    if n is None:
        abort(404)
    flash(f"Requeued {n} URL(s).")
    return redirect(url_for("seeds.index"))

@bp.route("/seeds/<int:seed_id>/delete", methods=["GET", "POST"])
def delete(seed_id):
    conn = get_conn()
    seed = seeds_ops.get_seed(conn, seed_id)
    if seed is None:
        abort(404)
    if request.method == "GET":
        return render_template("seed_delete.html", seed=seed)
    result = seeds_ops.delete_seed(conn, seed_id)
    flash(f"Seed deleted: {result['queued_removed']} queued URL(s) removed, {result['pages_kept']} page(s) kept.")
    return redirect(url_for("seeds.index"))
