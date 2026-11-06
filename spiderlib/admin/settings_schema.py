"""Editable crawler settings: field definitions, validation and applying a form.

Usage:
    changes, errors = apply_changes(conn, request.form)
    for title, fields in groups(): ...
"""

import math

from spiderlib import db

FIELDS = (
    {"key": "user_agent", "label": "User-Agent", "group": "Politeness", "kind": "str", "min": 1, "max": 200, "help": "Sent with every request. Include a contact URL."},
    {"key": "respect_robots", "label": "Respect robots.txt", "group": "Politeness", "kind": "bool", "min": None, "max": None, "help": "Turn off to ignore robots.txt completely."},
    {"key": "default_delay", "label": "Delay per host (seconds)", "group": "Politeness", "kind": "float", "min": 0, "max": 3600, "help": "Minimum time between requests to one host."},
    {"key": "concurrency", "label": "Workers", "group": "Politeness", "kind": "int", "min": 1, "max": 32, "help": "Number of parallel fetch threads."},
    {"key": "timeout", "label": "Request timeout (seconds)", "group": "Limits", "kind": "float", "min": 1, "max": 300, "help": "Give up on a request after this long."},
    {"key": "max_bytes", "label": "Max page size (bytes)", "group": "Limits", "kind": "int", "min": 1000, "max": 50000000, "help": "Larger pages are cut off."},
    {"key": "max_depth", "label": "Max depth", "group": "Limits", "kind": "int", "min": 0, "max": 50, "help": "Link depth from the seed. A seed can override this."},
    {"key": "max_pages_per_domain", "label": "Max pages per domain", "group": "Limits", "kind": "int", "min": 1, "max": 10000000, "help": "Stop adding URLs for a host after this many."},
    {"key": "allow_external", "label": "Follow external links", "group": "Limits", "kind": "bool", "min": None, "max": None, "help": "Default for seeds that do not set it."},
    {"key": "max_retries", "label": "Max retries", "group": "Retries", "kind": "int", "min": 0, "max": 10, "help": "For timeouts, connection errors and 5xx."},
    {"key": "retry_backoff_seconds", "label": "Retry backoff (seconds)", "group": "Retries", "kind": "int", "min": 0, "max": 86400, "help": "Wait attempts x this before a retry."},
)

def groups():
    groups_dict = {}
    for field in FIELDS:
        if field['group'] not in groups_dict:
            groups_dict[field['group']] = []
        groups_dict[field['group']].append(field)
    return [(group, fields) for group, fields in groups_dict.items()]

def validate(field, text):
    kind = field['kind']
    if kind == "bool":
        return None, None
    elif kind == "str":
        stripped_text = text.strip()
        if len(stripped_text) < field['min'] or len(stripped_text) > field['max']:
            return None, f"must be {field['min']}-{field['max']} characters"
        if any(ord(char) < 32 for char in stripped_text):
            return None, "contains control characters"
        return stripped_text, None
    elif kind == "int":
        try:
            value = int(text.strip())
        except ValueError:
            return None, "must be a whole number"
        if value < field['min'] or value > field['max']:
            return None, f"must be between {field['min']} and {field['max']}"
        return value, None
    elif kind == "float":
        try:
            value = float(text.strip())
        except ValueError:
            return None, "must be a number"
        if not math.isfinite(value):
            return None, "must be a number"
        if not (field['min'] <= value <= field['max']):
            return None, f"must be between {field['min']} and {field['max']}"
        return value, None
    return None, None

def apply_changes(conn, form):
    errors = {}
    new_values = {}
    for field in FIELDS:
        key = field['key']
        kind = field['kind']
        if kind == "bool":
            new_values[key] = key in form
        elif key in form:
            value, error = validate(field, form[key])
            if error:
                errors[key] = error
            else:
                new_values[key] = value

    if errors:
        return [], errors

    current = db.get_settings(conn)
    changes = []
    for key, new in new_values.items():
        if current.get(key) != new:
            db.set_setting(conn, key, new)
            db.audit(conn, "admin", "set_setting", f"{key}: {current[key]} -> {new}")
            changes.append((key, current[key], new))

    return changes, {}
