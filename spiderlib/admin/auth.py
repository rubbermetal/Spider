"""Admin login, logout, CSRF protection and the app-wide request guard."""

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, session, url_for
import hmac
import secrets
import time

MAX_FAILS = 5
WINDOW = 300
FAILS = {}
bp = Blueprint("auth", __name__)

def client_ip():
    if current_app.config.get("TRUST_PROXY"):
        return request.headers.get("X-Real-IP") or request.remote_addr or "?"
    return request.remote_addr or "?"

def locked(ip, now=None):
    now = now or time.time()
    FAILS[ip] = [ts for ts in FAILS.get(ip, []) if now - ts < WINDOW]
    return len(FAILS[ip]) >= MAX_FAILS

def record_failure(ip):
    FAILS.setdefault(ip, []).append(time.time())

def csrf_token() -> str:
    return session.setdefault("csrf", secrets.token_hex(16))

def guard():
    if request.endpoint is None or request.endpoint == "static" or request.endpoint.startswith("static"):
        return None
    if not current_app.config.get("PASSWORD"):
        return ("Admin password not configured.", 503)
    if request.method == "POST":
        submitted = request.form.get("csrf") or request.headers.get("X-CSRF-Token") or ""
        expected = session.get("csrf")
        if not expected or not hmac.compare_digest(submitted, expected):
            abort(400)
    if request.endpoint != "auth.login" and not session.get("admin"):
        nxt = request.full_path.rstrip("?")
        if nxt.startswith("/api/"):
            return (jsonify(error="login required"), 401)
        return redirect(url_for("auth.login", next=nxt))
    return None

@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)
    ip = client_ip()
    if locked(ip):
        return ("Too many attempts.", 429)
    submitted = request.form.get("password", "")
    if hmac.compare_digest(submitted.encode("utf-8"), current_app.config["PASSWORD"].encode("utf-8")):
        FAILS.pop(ip, None)
        session.clear()
        session["admin"] = True
        session["csrf"] = secrets.token_hex(16)
        nxt = request.args.get("next", "/")
        if not nxt.startswith("/") or nxt.startswith("//"):
            nxt = "/"
        return redirect(nxt)
    record_failure(ip)
    return (render_template("login.html", error="Invalid password"), 401)

@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
