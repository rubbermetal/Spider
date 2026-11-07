"""Bulk and single actions on rows of the urls table (requeue, hide, approve, tag, delete)."""

import re
from spiderlib import db

ACTIONS = ("requeue", "hide", "unhide", "approve", "unapprove", "delete", "tag_add", "tag_remove")
MAX_IDS = 1000

def parse_ids(values):
    seen = set()
    result = []
    for value in values:
        try:
            num = int(value)
            if num >= 1 and num not in seen:
                seen.add(num)
                result.append(num)
                if len(result) >= MAX_IDS:
                    break
        except ValueError:
            pass
    return result

def clean_tag(text):
    tag = text.strip().lower()
    if re.match(r'^[a-z0-9_-]{1,30}$', tag):
        return tag
    return None

def apply_action(conn, action, ids, value=""):
    if action not in ACTIONS:
        return (0, "unknown action")
    if not ids:
        return (0, "nothing selected")

    marks = ",".join("?" * len(ids))
    count = 0
    error = None

    if action == "requeue":
        cur = conn.execute(f"UPDATE urls SET status = 'queued', attempts = 0, next_attempt_at = NULL, error = NULL WHERE id IN ({marks})", ids)
        count = cur.rowcount
    elif action in ("hide", "unhide"):
        hidden_value = 1 if action == "hide" else 0
        cur = conn.execute(f"UPDATE urls SET hidden = {hidden_value} WHERE id IN ({marks})", ids)
        count = cur.rowcount
    elif action in ("approve", "unapprove"):
        approved_value = 1 if action == "approve" else 0
        cur = conn.execute(f"UPDATE urls SET approved = {approved_value} WHERE id IN ({marks})", ids)
        count = cur.rowcount
    elif action == "delete":
        conn.execute(f"DELETE FROM links WHERE from_id IN ({marks})", ids)
        conn.execute(f"UPDATE urls SET discovered_from = NULL WHERE discovered_from IN ({marks})", ids)
        cur = conn.execute(f"DELETE FROM urls WHERE id IN ({marks})", ids)
        count = cur.rowcount
    elif action in ("tag_add", "tag_remove"):
        tag = clean_tag(value)
        if tag is None:
            return (0, "invalid tag (letters, digits, - or _, up to 30)")
        rows = conn.execute(f"SELECT id, tags FROM urls WHERE id IN ({marks})", ids).fetchall()
        for row in rows:
            tags = [t.strip() for t in row['tags'].split(",") if t.strip()]
            if action == "tag_add" and tag not in tags:
                tags.append(tag)
            elif action == "tag_remove" and tag in tags:
                tags.remove(tag)
            if tags != [t.strip() for t in row['tags'].split(",") if t.strip()]:
                conn.execute("UPDATE urls SET tags = ? WHERE id = ?", (",".join(tags), row['id']))
                count += 1

    conn.commit()
    detail = f"{count} of {len(ids)} url(s)"
    if action in ("tag_add", "tag_remove"):
        detail += f" tag={tag}"
    db.audit(conn, "admin", "url_" + action, detail)

    return (count, error)
