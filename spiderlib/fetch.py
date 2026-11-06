"""Polite single-page fetcher and per-host rate limiter.

Usage:
    settings = {"user_agent": "SpiderBot/1.0", "timeout": 15.0, "max_bytes": 2000000}
    throttle = HostThrottle()
    throttle.wait("example.com", 2.0)
    r = fetch("https://example.com/", settings)
    if r["ok"] and not r["skipped_reason"]:
        html = r["body"]
    else:
        print(r["error_kind"], r["error"])
"""
import time
import threading
import zlib
import ssl
import socket
import urllib.request
import urllib.error

HTML_TYPES = ("text/html", "application/xhtml+xml")
MAX_REDIRECTS = 5

class _Redirects(urllib.request.HTTPRedirectHandler):
    max_redirections = MAX_REDIRECTS

def fetch(url: str, settings: dict, opener=None) -> dict:
    result = {
        "ok": False,
        "status": None,
        "final_url": url,
        "content_type": "",
        "body": b"",
        "truncated": False,
        "elapsed_ms": 0,
        "error": None,
        "error_kind": None,
        "skipped_reason": None
    }

    start_time = time.monotonic()

    try:
        if opener is None:
            opener = urllib.request.build_opener(_Redirects)

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": settings["user_agent"],
                "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.1",
                "Accept-Encoding": "gzip"
            }
        )

        with opener.open(req, timeout=settings["timeout"]) as response:
            result["status"] = response.status
            result["final_url"] = response.geturl()
            content_type = response.headers.get("Content-Type", "")
            result["content_type"] = content_type

            media = content_type.split(";")[0].strip().lower()
            if media and media not in HTML_TYPES:
                result["ok"] = True
                result["skipped_reason"] = "content-type"
                return result

            body = response.read(settings["max_bytes"] + 1)
            if len(body) > settings["max_bytes"]:
                body = body[:settings["max_bytes"]]
                result["truncated"] = True

            if response.headers.get("Content-Encoding", "").strip().lower() == "gzip":
                try:
                    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
                    body = decompressor.decompress(body, settings["max_bytes"])
                    if decompressor.unconsumed_tail:
                        result["truncated"] = True
                except zlib.error:
                    result["error"] = "bad gzip data"
                    result["error_kind"] = "other"
                    return result

            result["body"] = body
            result["ok"] = 200 <= result["status"] <= 299

    except urllib.error.HTTPError as e:
        result["status"] = e.code
        result["final_url"] = e.geturl() if e.geturl() else url
        result["error"] = f"HTTP {e.code}"
        if 300 <= e.code < 400:
            result["error_kind"] = "redirects"
        else:
            result["error_kind"] = "http"
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.gaierror):
            result["error_kind"] = "dns"
        elif isinstance(e.reason, (socket.timeout, TimeoutError)):
            result["error_kind"] = "timeout"
        elif isinstance(e.reason, (ssl.SSLError, ssl.CertificateError)):
            result["error_kind"] = "ssl"
        else:
            result["error_kind"] = "connection"
        result["error"] = str(e.reason)
    except (socket.timeout, TimeoutError):
        result["error_kind"] = "timeout"
        result["error"] = "timed out"
    except ssl.SSLError as e:
        result["error_kind"] = "ssl"
        result["error"] = str(e)
    except (ConnectionError, OSError) as e:
        result["error_kind"] = "connection"
        result["error"] = str(e)
    except Exception as e:
        result["error_kind"] = "other"
        result["error"] = str(e)

    finally:
        result["elapsed_ms"] = int((time.monotonic() - start_time) * 1000)

    return result

class HostThrottle:
    def __init__(self, clock=time.monotonic, sleep=time.sleep):
        self._clock = clock
        self._sleep = sleep
        self._next = {}
        self._lock = threading.Lock()

    def wait(self, host: str, delay: float) -> float:
        with self._lock:
            now = self._clock()
            slot = max(now, self._next.get(host, 0.0))
            self._next[host] = slot + delay
        if slot > now:
            self._sleep(slot - now)
        return max(0, slot - now)
