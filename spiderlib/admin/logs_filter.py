"""
Module to parse query strings for event log and audit log pages.
"""

LEVELS = ("info", "warn", "error")
PER_PAGE_CHOICES = (25, 50, 100, 200)

def _text(args, name, limit):
    return args.get(name, "").strip()[:limit]

def _page(args):
    page = args.get("page", "")
    if page.isdigit() and int(page) >= 1:
        return int(page)
    return 1

def _per_page(args):
    per_page = args.get("per_page", "")
    if per_page.isdigit() and int(per_page) in PER_PAGE_CHOICES:
        return int(per_page)
    return 50

def parse_log_args(args):
    return {
        "q": _text(args, "q", 200),
        "level": _text(args, "level", 200) if _text(args, "level", 200) in LEVELS else "",
        "page": _page(args),
        "per_page": _per_page(args)
    }

def parse_audit_args(args):
    return {
        "q": _text(args, "q", 200),
        "actor": _text(args, "actor", 50),
        "action": _text(args, "action", 60),
        "page": _page(args),
        "per_page": _per_page(args)
    }

def query_dict(f):
    result = {}
    if f.get("q"):
        result["q"] = f["q"]
    if f.get("level") and f["level"] in LEVELS:
        result["level"] = f["level"]
    if f.get("actor"):
        result["actor"] = f["actor"]
    if f.get("action"):
        result["action"] = f["action"]
    if f.get("per_page") and f["per_page"] != 50:
        result["per_page"] = f["per_page"]
    return result
