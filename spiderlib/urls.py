"""URL helpers for the crawler.

Usage:
    normalize_url("HTTP://Example.com:80/a?utm_source=x&b=2&a=1#top")
        -> "http://example.com/a?a=1&b=2"
    normalize_url("../up", base="http://example.com/a/b/c") -> "http://example.com/a/up"
    normalize_url("mailto:a@b.com") -> None
    is_same_site("http://a.example.com/", "https://b.example.com/") -> True
    has_skipped_extension("http://x.com/pic.jpg") -> True
"""
import urllib.parse

# Constants
TRACKING_PARAMS = {"fbclid", "gclid", "msclkid", "mc_cid", "mc_eid", "ref", "igshid"}
DEFAULT_SKIP_EXTENSIONS = (
    ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".bmp", ".pdf", ".zip", ".gz", ".tar", ".tgz", ".rar", ".7z",
    ".mp3", ".mp4", ".avi", ".mov", ".mkv", ".wav", ".flac", ".exe", ".dmg", ".iso", ".bin", ".css", ".js", ".json", ".xml",
    ".woff", ".woff2", ".ttf", ".eot", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx"
)

def normalize_url(url: str, base: str | None = None) -> str | None:
    """
    Returns a canonical absolute URL string, or None if the URL is unusable.
    """
    url = url.strip()
    if not url:
        return None

    if base:
        url = urllib.parse.urljoin(base, url)

    try:
        parsed_url = urllib.parse.urlsplit(url)
    except ValueError:
        return None

    scheme = parsed_url.scheme.lower()
    if scheme not in ("http", "https"):
        return None

    hostname = parsed_url.hostname
    if not hostname:
        return None

    try:
        hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        return None

    hostname = hostname.rstrip(".")

    netloc = hostname
    if parsed_url.port:
        if parsed_url.port not in (80 if scheme == "http" else 443,):
            netloc += f":{parsed_url.port}"

    path = parsed_url.path or "/"
    query = urllib.parse.parse_qsl(parsed_url.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k.lower() not in TRACKING_PARAMS and not k.lower().startswith("utm_")]
    query = sorted(query)
    query = urllib.parse.urlencode(query)

    final_url = urllib.parse.urlunsplit((scheme, netloc, path, query, ""))
    if len(final_url) > 2000:
        return None

    return final_url

def host_of(url: str) -> str:
    """
    Returns the lowercase hostname of a URL ("" if it cannot be parsed). Port is NOT included.
    """
    try:
        parsed_url = urllib.parse.urlsplit(url)
        hostname = parsed_url.hostname
        if hostname:
            return hostname.lower().rstrip(".")
    except ValueError:
        pass
    return ""

def registered_domain(host: str) -> str:
    """
    Naive: return the last two dot-separated labels of the host.
    """
    parts = host.split(".")
    if len(parts) < 2 or all(part.isdigit() for part in parts):
        return host
    return ".".join(parts[-2:])

def is_same_site(url_a: str, url_b: str) -> bool:
    """
    True when registered_domain(host_of(url_a)) == registered_domain(host_of(url_b)) and the domain is not empty.
    """
    domain_a = registered_domain(host_of(url_a))
    domain_b = registered_domain(host_of(url_b))
    return domain_a == domain_b and domain_a != ""

def has_skipped_extension(url: str, extensions=DEFAULT_SKIP_EXTENSIONS) -> bool:
    """
    True if the URL path (lowercased, query ignored) ends with any of the extensions.
    """
    path = urllib.parse.urlsplit(url).path.lower()
    return any(path.endswith(ext) for ext in extensions)
