import csv
import io
import json
from datetime import datetime, timezone
from spiderlib.admin import urls_filter

COLUMNS = ["url", "host", "status", "http_status", "title", "description", "content_type", "depth", "fetched_at", "tags", "approved"]

def parse_options(args):
    fmt = (args.get("format", "") or "csv").strip().lower() or "csv"
    if fmt not in ["csv", "json"]:
        return (None, "format must be csv or json")
    
    status = args.get("status", "").strip()
    if status and status not in urls_filter.STATUSES:
        return (None, "unknown status")
    
    hidden = args.get("hidden", "exclude").strip().lower()
    if hidden not in ["exclude", "include"]:
        return (None, "hidden must be exclude or include")
    
    approved = args.get("approved", "any").strip().lower()
    if approved not in ["any", "only"]:
        return (None, "approved must be any or only")
    
    return ({"format": fmt, "status": status, "hidden": hidden, "approved": approved}, None)

def _where(opts):
    conditions = []
    params = []
    
    if opts["status"]:
        conditions.append("status = ?")
        params.append(opts["status"])
    
    if opts["hidden"] == "exclude":
        conditions.append("hidden = 0")
    
    if opts["approved"] == "only":
        conditions.append("approved = 1")
    
    return (" WHERE " + " AND ".join(conditions) if conditions else "", params)

def count_rows(conn, opts):
    sql, params = _where(opts)
    cursor = conn.cursor()
    cursor.execute(f"SELECT COUNT(*) FROM urls{sql}", params)
    return cursor.fetchone()[0]

def fetch_rows(conn, opts):
    sql, params = _where(opts)
    cursor = conn.cursor()
    cursor.execute(f"SELECT {', '.join(COLUMNS)} FROM urls{sql} ORDER BY id", params)
    return [tuple(row) for row in cursor.fetchall()]

def render(conn, opts):
    rows = fetch_rows(conn, opts)
    
    if opts["format"] == "csv":
        output = io.StringIO(newline="")
        writer = csv.writer(output)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
        body = output.getvalue()
        output.close()
        mimetype = "text/csv; charset=utf-8"
        filename = f"spider-urls-{datetime.now(timezone.utc).strftime('%Y%m%d')}.csv"
    
    elif opts["format"] == "json":
        rows = [dict(zip(COLUMNS, r), approved=bool(r[COLUMNS.index("approved")])) for r in rows]
        body = json.dumps(rows, indent=2, ensure_ascii=False)
        mimetype = "application/json; charset=utf-8"
        filename = f"spider-urls-{datetime.now(timezone.utc).strftime('%Y%m%d')}.json"
    
    return (body, mimetype, filename)
