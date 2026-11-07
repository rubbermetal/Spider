"""Export page: download the crawled URLs as CSV or JSON."""

from flask import Blueprint, Response, render_template, request
from spiderlib.admin import export_ops, urls_filter
from spiderlib.admin.dbconn import get_conn

bp = Blueprint("export", __name__)

@bp.route("/export")
def index():
    opts, error = export_ops.parse_options(request.args)
    if error:
        opts, _ = export_ops.parse_options({})
    count = export_ops.count_rows(get_conn(), opts)
    return render_template("export.html", opts=opts, error=error, count=count, statuses=urls_filter.STATUSES)

@bp.route("/export/download")
def download():
    opts, error = export_ops.parse_options(request.args)
    if error:
        return (error, 400)
    body, mimetype, filename = export_ops.render(get_conn(), opts)
    return Response(body, headers={"Content-Type": mimetype, "Content-Disposition": f'attachment; filename="{filename}"'})
