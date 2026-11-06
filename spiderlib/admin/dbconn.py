"""Per-request sqlite connection for the admin app."""

from flask import current_app, g
from spiderlib import db

def get_conn():
    if "conn" not in g:
        g.conn = db.connect(current_app.config["DB_PATH"])
    return g.conn

def close_conn(exc=None):
    conn = g.pop("conn", None)
    if conn is not None:
        conn.close()
