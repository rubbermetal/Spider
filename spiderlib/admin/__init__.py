"""Spider admin web app.

Usage example:
app = create_app("spider.db", password="s3cret"); app.run()
"""

import os
import secrets
from flask import Flask

def create_app(db_path, password=None, secret_key=None, trust_proxy=False, runner=None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")
    app.config["DB_PATH"] = db_path
    app.config["PASSWORD"] = password if password is not None else os.environ.get("SPIDER_ADMIN_PASSWORD", "")
    app.config["SECRET_KEY"] = secret_key or os.environ.get("SPIDER_SECRET") or secrets.token_hex(32)
    app.config["TRUST_PROXY"] = trust_proxy
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

    from spiderlib.admin import auth, dashboard, dbconn, seeds, settings, urls
    from spiderlib.admin.runner import Runner

    app.extensions["spider_runner"] = runner if runner is not None else Runner()
    app.teardown_appcontext(dbconn.close_conn)
    app.before_request(auth.guard)
    app.context_processor(lambda: {"csrf_token": auth.csrf_token})
    app.register_blueprint(auth.bp)
    app.register_blueprint(dashboard.bp)
    app.register_blueprint(seeds.bp)
    app.register_blueprint(settings.bp)
    app.register_blueprint(urls.bp)

    return app
