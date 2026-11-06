import gzip
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import pytest
from spiderlib.fetch import fetch, HostThrottle

# Settings
S = {
    "user_agent": "TestBot/1.0",
    "timeout": 5.0,
    "max_bytes": 1000
}

class SimpleHTTPRequestHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path == "/ok":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<html><title>Hi</title></html>")
        elif self.path == "/big":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"x" * 5000)
        elif self.path == "/pdf":
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.end_headers()
            self.wfile.write(b"%PDF-1.4")
        elif self.path == "/404":
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"nope")
        elif self.path == "/500":
            self.send_response(500)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"boom")
        elif self.path == "/redir":
            self.send_response(302)
            self.send_header("Location", "/ok")
            self.end_headers()
        elif self.path == "/loop":
            self.send_response(302)
            self.send_header("Location", "/loop")
            self.end_headers()
        elif self.path == "/gzip":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(gzip.compress(b"<html>zipped</html>"))
        elif self.path == "/gzipbomb":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Encoding", "gzip")
            self.end_headers()
            self.wfile.write(gzip.compress(b"a" * 100000))
        elif self.path == "/slow":
            time.sleep(1.5)
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"late")
        elif self.path == "/noctype":
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"plain")
        elif self.path == "/ua":
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(self.headers["User-Agent"].encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

@pytest.fixture(scope="module")
def server():
    server_address = ("127.0.0.1", 0)
    httpd = ThreadingHTTPServer(server_address, SimpleHTTPRequestHandler)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    server_thread.join()

def test_ok(server):
    result = fetch(server + "/ok", S)
    assert result["ok"] is True
    assert result["status"] == 200
    assert result["body"] == b"<html><title>Hi</title></html>"
    assert result["content_type"].startswith("text/html")
    assert result["error"] is None
    assert result["skipped_reason"] is None
    assert result["truncated"] is False
    assert result["elapsed_ms"] >= 0

def test_truncated(server):
    result = fetch(server + "/big", S)
    assert result["ok"] is True
    assert len(result["body"]) == 1000
    assert result["truncated"] is True

def test_non_html_skipped(server):
    result = fetch(server + "/pdf", S)
    assert result["ok"] is True
    assert result["body"] == b""
    assert result["skipped_reason"] == "content-type"

def test_404(server):
    result = fetch(server + "/404", S)
    assert result["ok"] is False
    assert result["status"] == 404
    assert result["error"] == "HTTP 404"
    assert result["error_kind"] == "http"

def test_500(server):
    result = fetch(server + "/500", S)
    assert result["ok"] is False
    assert result["status"] == 500
    assert result["error_kind"] == "http"

def test_redirect_followed(server):
    result = fetch(server + "/redir", S)
    assert result["ok"] is True
    assert result["final_url"] == server + "/ok"
    assert b"Hi" in result["body"]

def test_redirect_loop(server):
    result = fetch(server + "/loop", S)
    assert result["ok"] is False
    assert result["error_kind"] == "redirects"

def test_gzip(server):
    result = fetch(server + "/gzip", S)
    assert result["body"] == b"<html>zipped</html>"

def test_gzip_capped(server):
    result = fetch(server + "/gzipbomb", S)
    assert len(result["body"]) == 1000
    assert result["truncated"] is True

def test_timeout(server):
    result = fetch(server + "/slow", {**S, "timeout": 0.3})
    assert result["ok"] is False
    assert result["error_kind"] == "timeout"

def test_no_content_type_is_read(server):
    result = fetch(server + "/noctype", S)
    assert result["ok"] is True
    assert result["body"] == b"plain"

def test_connection_refused():
    result = fetch("http://127.0.0.1:1/", S)
    assert result["ok"] is False
    assert result["error_kind"] == "connection"

def test_dns_failure():
    result = fetch("http://nonexistent.invalid/", S)
    assert result["ok"] is False
    assert result["error_kind"] in ("dns", "connection")

def test_sends_user_agent(server):
    result = fetch(server + "/ua", S)
    assert result["body"] == b"TestBot/1.0"

class FakeClock:
    def __init__(self):
        self.t = 0.0
        self.sleeps = []

    def now(self):
        return self.t

    def sleep(self, s):
        self.sleeps.append(s)
        self.t += s

@pytest.fixture
def clock():
    return FakeClock()

@pytest.fixture
def throttle(clock):
    return HostThrottle(clock=clock.now, sleep=clock.sleep)

def test_throttle_first_request_no_wait(throttle, clock):
    result = throttle.wait("a.com", 2.0)
    assert result == 0.0
    assert clock.sleeps == []

def test_throttle_second_request_waits(throttle, clock):
    throttle.wait("a.com", 2.0)
    result = throttle.wait("a.com", 2.0)
    assert result == 2.0
    assert clock.sleeps == [2.0]

def test_throttle_different_hosts_independent(throttle, clock):
    throttle.wait("a.com", 2.0)
    result = throttle.wait("b.com", 2.0)
    assert result == 0.0

def test_throttle_after_delay_no_wait(throttle, clock):
    throttle.wait("a.com", 2.0)
    clock.t += 3.0
    result = throttle.wait("a.com", 2.0)
    assert result == 0.0

def test_throttle_threads_get_distinct_slots():
    t = HostThrottle()

    def worker(results):
        results.append(t.wait("a.com", 0.05))

    results = []
    threads = [threading.Thread(target=worker, args=(results,)) for _ in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert len(set(results)) == 4
    assert max(results) >= 0.1 - 0.02
