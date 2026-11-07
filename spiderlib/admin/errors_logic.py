import re

FIXED_KINDS = (
    "blocked-robots",
    "blocked-domain",
    "skipped-redirect",
    "timeout",
    "dns",
    "connection",
    "ssl",
    "redirects",
    "other"
)

def classify(status, http_status, error):
    err = (error or "").lower()
    if status == "blocked":
        return "blocked-domain" if "domain" in err else "blocked-robots"
    elif status == "skipped":
        return "skipped-redirect"
    elif http_status is not None and http_status >= 400:
        return f"http-{http_status}"
    elif "timed out" in err or "timeout" in err:
        return "timeout"
    elif any(sub in err for sub in (
        "name or service not known",
        "getaddrinfo",
        "nodename nor servname",
        "no address associated",
        "temporary failure in name resolution"
    )):
        return "dns"
    elif "ssl" in err or "certificate" in err:
        return "ssl"
    elif "redirect" in err:
        return "redirects"
    elif any(sub in err for sub in (
        "refused",
        "reset by peer",
        "unreachable",
        "connection",
        "broken pipe",
        "errno"
    )):
        return "connection"
    else:
        return "other"

def label(kind):
    if kind == "blocked-robots":
        return "Blocked by robots.txt"
    elif kind == "blocked-domain":
        return "Blocked domain"
    elif kind == "skipped-redirect":
        return "Skipped (redirect)"
    elif kind == "timeout":
        return "Timeouts"
    elif kind == "dns":
        return "DNS failures"
    elif kind == "connection":
        return "Connection errors"
    elif kind == "ssl":
        return "SSL / certificate errors"
    elif kind == "redirects":
        return "Too many redirects"
    elif kind == "other":
        return "Other errors"
    elif re.fullmatch(r"http-[0-9]{3}", kind):
        return f"HTTP {kind[5:]}"
    else:
        return kind

def is_valid_kind(kind):
    return kind in FIXED_KINDS or re.fullmatch(r"http-[0-9]{3}", kind)
