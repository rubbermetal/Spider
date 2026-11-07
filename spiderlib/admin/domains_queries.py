"""
This module provides functions to query and manage domain data.
"""

from spiderlib.admin import urls_filter

SORTS = ("host", "total", "done", "queued", "errors", "blocked")
PER_PAGE_CHOICES = (25, 50, 100)

def parse_args(args) -> dict:
    f = {}
    f["q"] = args.get("q", "").strip()[:200]
    blocked = args.get("blocked", "")
    f["blocked"] = blocked if blocked in ("yes", "no") else ""
    f["sort"] = args.get("sort", "total") if args.get("sort") in SORTS else "total"
    f["order"] = "asc" if args.get("order") == "asc" else "desc"
    page_text = args.get("page", "")
    f["page"] = int(page_text) if page_text.isdigit() and int(page_text) >= 1 else 1
    per_page_text = args.get("per_page", "")
    f["per_page"] = int(per_page_text) if per_page_text.isdigit() and int(per_page_text) in PER_PAGE_CHOICES else 50
    return f

def query_dict(f) -> dict:
    q = {}
    if f["q"]:
        q["q"] = f["q"]
    if f["blocked"]:
        q["blocked"] = f["blocked"]
    if f["sort"] != "total":
        q["sort"] = f["sort"]
    if f["order"] != "desc":
        q["order"] = f["order"]
    if f["per_page"] != 50:
        q["per_page"] = f["per_page"]
    return q

def list_domains(conn, f) -> tuple:
    cte = "WITH hosts AS (SELECT host FROM urls UNION SELECT host FROM domains) "
    base = "FROM hosts h LEFT JOIN domains d ON d.host = h.host"
    conds = []
    params = []
    
    if f["q"]:
        conds.append("h.host LIKE ? ESCAPE '\\'")
        params.append("%" + f["q"].replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
    if f["blocked"] == "yes":
        conds.append("COALESCE(d.blocked, 0) = 1")
    elif f["blocked"] == "no":
        conds.append("COALESCE(d.blocked, 0) = 0")
    where = " WHERE " + " AND ".join(conds) if conds else ""
    
    total_query = cte + "SELECT COUNT(*) " + base + where
    cursor = conn.execute(total_query, params)
    total = cursor.fetchone()[0]
    pg = urls_filter.pager(total, f["page"], f["per_page"])
    
    query = cte + """
    SELECT h.host AS host, COALESCE(d.blocked, 0) AS blocked, d.delay_override AS delay_override, COALESCE(d.notes, '') AS notes, d.robots_status AS robots_status, d.robots_fetched_at AS robots_fetched_at,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host) AS total,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host AND u.status = 'done') AS done,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host AND u.status IN ('queued', 'fetching')) AS queued,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host AND u.status = 'error') AS errors
    """ + base + where + f" ORDER BY {f['sort']} {'ASC' if f['order'] == 'asc' else 'DESC'}, host ASC LIMIT ? OFFSET ?"
    params.extend([pg["per_page"], pg["offset"]])
    cursor = conn.execute(query, params)
    rows = cursor.fetchall()
    
    return ([dict(r) for r in rows], pg)

def get_domain(conn, host) -> dict | None:
    query = """
    WITH hosts AS (SELECT host FROM urls UNION SELECT host FROM domains)
    SELECT h.host AS host, COALESCE(d.blocked, 0) AS blocked, d.delay_override AS delay_override, COALESCE(d.notes, '') AS notes, d.robots_status AS robots_status, d.robots_fetched_at AS robots_fetched_at, d.robots_txt AS robots_txt,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host) AS total,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host AND u.status = 'done') AS done,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host AND u.status IN ('queued', 'fetching')) AS queued,
           (SELECT COUNT(*) FROM urls u WHERE u.host = h.host AND u.status = 'error') AS errors
    FROM hosts h
    LEFT JOIN domains d ON d.host = h.host
    WHERE h.host = ?
    """
    cursor = conn.execute(query, (host,))
    row = cursor.fetchone()
    return dict(row) if row else None

def recent_urls(conn, host, limit=10) -> list:
    query = """
    SELECT id, url, status, http_status, title
    FROM urls
    WHERE host = ?
    ORDER BY id DESC
    LIMIT ?
    """
    cursor = conn.execute(query, (host, limit))
    return [dict(r) for r in cursor.fetchall()]
