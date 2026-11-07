"""Retry actions for the errors page."""

from spiderlib import db
from spiderlib.admin import errors_logic, errors_queries

def retry_group(conn, kind) -> int | None:
    """
    Retry actions for the errors page.
    
    :param conn: Database connection
    :param kind: Type of errors to retry
    :return: Number of requeued items or None if kind is invalid
    """
    if not errors_logic.is_valid_kind(kind):
        return None

    ids = errors_queries.ids_in_group(conn, kind)
    n = 0

    for i in range(0, len(ids), 500):
        chunk = ids[i:i + 500]
        marks = ",".join("?" * len(chunk))
        cur = conn.execute(f"UPDATE urls SET status = 'queued', attempts = 0, next_attempt_at = NULL, error = NULL WHERE id IN ({marks})", chunk)
        n += cur.rowcount

    conn.commit()
    db.audit(conn, "admin", "errors_retry_group", f"{kind}: requeued {n}")
    return n
