"""The `serve` command: run the web admin.

Usage:
    spider serve --host 127.0.0.1 --port 8080 --password SECRET
The password may also come from the SPIDER_ADMIN_PASSWORD environment variable.
"""

import os
import sys

def add_arguments(subparsers):
    p = subparsers.add_parser("serve", help="Run the web admin")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8080)
    p.add_argument("--password", default=None)
    p.add_argument("--trust-proxy", action="store_true", help="trust the X-Real-IP header, use behind a reverse proxy")
    return p

def cmd_serve(conn, args) -> int:
    password = args.password if args.password is not None else os.environ.get("SPIDER_ADMIN_PASSWORD", "")
    if not password:
        print("no admin password: pass --password or set SPIDER_ADMIN_PASSWORD", file=sys.stderr)
        return 2
    conn.close()
    from spiderlib.admin import create_app
    app = create_app(args.db, password=password, trust_proxy=args.trust_proxy)
    print(f"spider admin on http://{args.host}:{args.port}/")
    app.run(host=args.host, port=args.port, threaded=True)
    return 0
