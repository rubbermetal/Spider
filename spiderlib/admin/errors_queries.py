"""Read-only queries for the errors page: groups, group listing, top hosts."""

from spiderlib.admin import errors_logic, urls_filter

PROBLEM_STATUSES = ("error", "blocked", "skipped")
MAX_GROUP_IDS = 10000

def _problem_rows(conn):
    query = """
    SELECT id, url, host, status, http_status, error, attempts, fetched_at
    FROM urls
    WHERE status IN (?, ?, ?)
    ORDER BY id
    """
    cursor = conn.execute(query, PROBLEM_STATUSES)
    rows = cursor.fetchall()
    return [{"kind": errors_logic.classify(row["status"], row["http_status"], row["error"]), **dict(row)} for row in rows]

def group_counts(conn):
    rows = _problem_rows(conn)
    grouped = {}
    for row in rows:
        kind = row["kind"]
        if kind not in grouped:
            grouped[kind] = {
                "kind": kind,
                "label": errors_logic.label(kind),
                "count": 0,
                "hosts": set(),
                "max_id": None
            }
        grouped[kind]["count"] += 1
        grouped[kind]["hosts"].add(row["host"])
        if grouped[kind]["max_id"] is None or row["id"] > grouped[kind]["max_id"]:
            grouped[kind]["max_id"] = row["id"]

    result = list(grouped.values())
    by_id = {r["id"]: r for r in rows}
    for group in result:
        group["hosts"] = len(group["hosts"])
        group["sample"] = by_id[group.pop("max_id")]["error"] or ""

    result.sort(key=lambda x: (-x["count"], x["kind"]))
    return result

def list_group(conn, kind, page=1, per_page=50):
    rows = _problem_rows(conn)
    matching = [r for r in rows if r["kind"] == kind]
    matching.reverse()
    pg = urls_filter.pager(len(matching), page, per_page)
    rows = matching[pg["offset"]: pg["offset"] + pg["per_page"]]
    return (rows, pg)

def ids_in_group(conn, kind):
    rows = _problem_rows(conn)
    return [r["id"] for r in rows if r["kind"] == kind][:MAX_GROUP_IDS]

def top_hosts(conn, limit=10):
    query = """
    SELECT host, COUNT(*) AS count
    FROM urls
    WHERE status IN (?, ?, ?)
    GROUP BY host
    ORDER BY count DESC, host ASC
    LIMIT ?
    """
    cursor = conn.execute(query, (*PROBLEM_STATUSES, limit))
    rows = cursor.fetchall()
    return [{"host": row["host"], "count": row["count"]} for row in rows]

def total_problems(conn):
    query = """
    SELECT COUNT(*)
    FROM urls
    WHERE status IN (?, ?, ?)
    """
    cursor = conn.execute(query, PROBLEM_STATUSES)
    row = cursor.fetchone()
    return row[0]
