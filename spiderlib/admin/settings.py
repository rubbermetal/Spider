"""Settings admin page: typed form for the crawler settings."""

from flask import Blueprint, flash, redirect, render_template, request, url_for
from spiderlib import db
from spiderlib.admin import settings_schema
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("settings", __name__)

@bp.route("/settings", methods=["GET", "POST"])
def edit():
    conn = get_conn()
    current = db.get_settings(conn)
    
    if request.method == "GET":
        return render_template("settings.html", groups=settings_schema.groups(), values=current, errors={}, state=current["crawl_state"])
    
    changes, errors = settings_schema.apply_changes(conn, request.form)
    
    if errors:
        values = current.copy()
        for key in request.form:
            if key in errors:
                values[key] = request.form[key]
        return render_template("settings.html", groups=settings_schema.groups(), values=values, errors=errors, state=current["crawl_state"]), 400
    
    flash(f"Saved {len(changes)} change(s)." if changes else "No changes.")
    return redirect(url_for("settings.edit"))
