"""
Module for handling log and audit queries in the spiderlib admin system.
"""

from datetime import datetime, timedelta, timezone
from spiderlib import db
from spiderlib.admin import urls_filter

def _like(text):
    return "%" + text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"

def list_log(conn, f):
    conditions = []
    params = []
    if f.get("level"):
        conditions.append("level = ?")
        params.append(f["level"])
    if f.get("q"):
        conditions.append("message LIKE ? ESCAPE '\\'")
        params.append(_like(f["q"]))

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"SELECT COUNT(*) FROM log{where}"
    total = conn.execute(query, params).fetchone()[0]
    pg = urls_filter.pager(total, f["page"], f["per_page"])

    query = f"SELECT id, ts, level, message FROM log{where} ORDER BY id DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [pg["per_page"], pg["offset"]]).fetchall()
    return ([dict(r) for r in rows], pg)

def list_audit(conn, f):
    conditions = []
    params = []
    if f.get("actor"):
        conditions.append("actor = ?")
        params.append(f["actor"])
    if f.get("action"):
        conditions.append("action = ?")
        params.append(f["action"])
    if f.get("q"):
        conditions.append("(detail LIKE ? ESCAPE '\\' OR action LIKE ? ESCAPE '\\')")
        params.extend([_like(f["q"]), _like(f["q"])])  # Corrected line

    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    query = f"SELECT COUNT(*) FROM audit{where}"
    total = conn.execute(query, params).fetchone()[0]
    pg = urls_filter.pager(total, f["page"], f["per_page"])

    query = f"SELECT id, ts, actor, action, detail FROM audit{where} ORDER BY id DESC LIMIT ? OFFSET ?"
    rows = conn.execute(query, params + [pg["per_page"], pg["offset"]]).fetchall()
    return ([dict(r) for r in rows], pg)

def audit_options(conn):
    actors = conn.execute("SELECT DISTINCT actor FROM audit").fetchall()
    actions = conn.execute("SELECT DISTINCT action FROM audit").fetchall()
    return {
        "actors": sorted([row[0] for row in actors]),
        "actions": sorted([row[0] for row in actions])
    }

def prune_log(conn, days):
    if type(days) is not int or not (1 <= days <= 3650):
        return None
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    cur = conn.execute("DELETE FROM log WHERE ts < ?", (cutoff,))
    n = cur.rowcount
    conn.commit()
    db.audit(conn, "admin", "logs_prune", f"older than {days} days: removed {n}")
    return n
