"""Database actions behind the seeds admin page: list, add, edit, enable/disable, recrawl, delete."""

from spiderlib import db, queue
from spiderlib.urls import normalize_url
from spiderlib.admin import seeds_form

def get_seed(conn, seed_id):
    """Retrieve a seed by its ID."""
    cursor = conn.execute("SELECT * FROM seeds WHERE id = ?", (seed_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def list_seeds(conn):
    """List all seeds with associated URL counts."""
    query = """
    SELECT seeds.*, 
           (SELECT COUNT(*) FROM urls WHERE urls.seed_id = seeds.id) AS total,
           (SELECT COUNT(*) FROM urls WHERE urls.seed_id = seeds.id AND status IN ('queued', 'fetching')) AS queued,
           (SELECT COUNT(*) FROM urls WHERE urls.seed_id = seeds.id AND status = 'done') AS done,
           (SELECT COUNT(*) FROM urls WHERE urls.seed_id = seeds.id AND status = 'error') AS errors
    FROM seeds
    ORDER BY seeds.id
    """
    cursor = conn.execute(query)
    return [dict(row) for row in cursor]

def add_from_form(conn, form):
    """Add a new seed from a form."""
    url = form.get("url", "").strip()
    values, errors = seeds_form.parse_limits(form)
    if not url:
        errors["url"] = "required"
    else:
        normalized = normalize_url(url)
        if normalized is None:
            errors["url"] = "not a valid http or https URL"
        else:
            cursor = conn.execute("SELECT * FROM seeds WHERE url = ?", (normalized,))
            if cursor.fetchone():
                errors["url"] = "seed already exists"

    if errors:
        return (None, errors)

    seed_id = queue.add_seed(
        conn,
        normalized,
        max_depth=values["max_depth"],
        max_pages=values["max_pages"],
        allow_external=values["allow_external"],
        recrawl_hours=values["recrawl_hours"]
    )
    db.audit(conn, "admin", "seed_add", normalized)
    return (seed_id, {})

def update_from_form(conn, seed_id, form):
    """Update an existing seed from a form."""
    seed = get_seed(conn, seed_id)
    if seed is None:
        return (False, {"seed": "not found"})

    values, errors = seeds_form.parse_limits(form)
    if errors:
        return (False, errors)

    conn.execute(
        "UPDATE seeds SET max_depth = ?, max_pages = ?, allow_external = ?, recrawl_hours = ? WHERE id = ?",
        (values["max_depth"], values["max_pages"], None if values["allow_external"] is None else int(values["allow_external"]), values["recrawl_hours"], seed_id)
    )
    conn.commit()
    db.audit(
        conn,
        "admin",
        "seed_edit",
        f"{seed['url']}: depth={values['max_depth']} pages={values['max_pages']} external={values['allow_external']} recrawl={values['recrawl_hours']}"
    )
    return (True, {})

def set_enabled(conn, seed_id, enabled):
    """Enable or disable a seed."""
    seed = get_seed(conn, seed_id)
    if seed is None:
        return False

    conn.execute("UPDATE seeds SET enabled = ? WHERE id = ?", (1 if enabled else 0, seed_id))
    conn.commit()
    action = "seed_enable" if enabled else "seed_disable"
    db.audit(conn, "admin", action, seed['url'])
    return True

def recrawl(conn, seed_id):
    """Recrawl a seed by requeuing its URLs."""
    seed = get_seed(conn, seed_id)
    if seed is None:
        return None

    cursor = conn.execute(
        "UPDATE urls SET status = 'queued', attempts = 0, next_attempt_at = NULL, error = NULL WHERE seed_id = ? AND status IN ('done', 'error', 'skipped', 'blocked')",
        (seed_id,)
    )
    n = cursor.rowcount
    conn.commit()
    db.audit(conn, "admin", "seed_recrawl", f"{seed['url']}: requeued {n}")
    return n

def delete_seed(conn, seed_id):
    """Delete a seed and its associated URLs."""
    seed = get_seed(conn, seed_id)
    if seed is None:
        return None

    cursor = conn.execute("DELETE FROM urls WHERE seed_id = ? AND status = 'queued'", (seed_id,))
    removed = cursor.rowcount
    kept = conn.execute("UPDATE urls SET seed_id = NULL WHERE seed_id = ?", (seed_id,)).rowcount
    conn.execute("DELETE FROM seeds WHERE id = ?", (seed_id,))
    conn.commit()
    db.audit(conn, "admin", "seed_delete", f"{seed['url']}: removed {removed} queued, kept {kept} pages")
    return {"queued_removed": removed, "pages_kept": kept}
