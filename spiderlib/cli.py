#!/usr/bin/env python3
"""
Spider command-line interface.

Usage examples:
1. Seed a new URL:
   spider seed add http://example.com --max-depth 2 --max-pages 10 --external --recrawl-hours 24

2. List all seeds:
   spider seed list

3. Get configuration settings:
   spider config

4. Set a configuration setting:
   spider config max_depth 5

5. Get the current status:
   spider status

6. Run the crawler:
   spider run --concurrency 5 --delay 1 --ignore-robots --forever

7. Pause the crawler:
   spider pause

8. Resume the crawler:
   spider resume

9. Stop the crawler:
   spider stop

10. Block a domain:
    spider block example.com

11. Unblock a domain:
    spider unblock example.com

12. Retry all errors:
    spider retry-errors

13. Export data:
    spider export --format csv --status done --out output.csv
"""

import argparse
import csv
import json
import os
import sys
from spiderlib import db, queue, crawler
from spiderlib.crawler import Crawler
from spiderlib.urls import host_of

def build_parser():
    parser = argparse.ArgumentParser(description="Spider command-line interface.")
    parser.add_argument('--db', default=os.getenv('SPIDER_DB', 'spider.db'), help="Database path")

    subparsers = parser.add_subparsers(dest="command", required=True)

    # seed add
    seed_add_parser = subparsers.add_parser('seed', help='Seed management')
    seed_add_subparsers = seed_add_parser.add_subparsers(dest='subcommand', required=True)
    seed_add = seed_add_subparsers.add_parser('add', help='Add a new seed')
    seed_add.add_argument('URL', help='URL to seed')
    seed_add.add_argument('--max-depth', type=int, help='Maximum depth')
    seed_add.add_argument('--max-pages', type=int, help='Maximum pages')
    ext_group = seed_add.add_mutually_exclusive_group()
    ext_group.add_argument('--external', action='store_true', help='Allow external URLs')
    ext_group.add_argument('--no-external', action='store_true', help='Disallow external URLs')
    seed_add.add_argument('--recrawl-hours', type=int, help='Recrawl hours')

    # seed list
    seed_list = seed_add_subparsers.add_parser('list', help='List all seeds')

    # config
    config_parser = subparsers.add_parser('config', help='Configuration management')
    config_parser.add_argument('KEY', nargs='?', help='Configuration key')
    config_parser.add_argument('VALUE', nargs='?', help='Configuration value')

    # status
    status = subparsers.add_parser('status', help='Get the current status')

    # run
    run_parser = subparsers.add_parser('run', help='Run the crawler')
    run_parser.add_argument('--concurrency', type=int, help='Concurrency level')
    run_parser.add_argument('--delay', type=float, help='Delay between requests')
    robots_group = run_parser.add_mutually_exclusive_group()
    robots_group.add_argument('--ignore-robots', action='store_true', help='Ignore robots.txt')
    robots_group.add_argument('--respect-robots', action='store_true', help='Respect robots.txt')
    run_parser.add_argument('--forever', action='store_true', help='Run forever')

    # pause, resume, stop
    pause = subparsers.add_parser('pause', help='Pause the crawler')
    resume = subparsers.add_parser('resume', help='Resume the crawler')
    stop = subparsers.add_parser('stop', help='Stop the crawler')

    # block, unblock
    block_parser = subparsers.add_parser('block', help='Block a domain')
    block_parser.add_argument('DOMAIN', help='Domain to block')
    unblock_parser = subparsers.add_parser('unblock', help='Unblock a domain')
    unblock_parser.add_argument('DOMAIN', help='Domain to unblock')

    # retry-errors
    retry_errors = subparsers.add_parser('retry-errors', help='Retry all errors')

    # export
    export_parser = subparsers.add_parser('export', help='Export data')
    export_parser.add_argument('--format', choices=['csv', 'json'], default='csv', help='Export format')
    export_parser.add_argument('--status', help='Filter by status')
    export_parser.add_argument('--out', help='Output file')

    return parser

def cmd_seed_add(conn, args):
    allow_external = None
    if args.external:
        allow_external = True
    elif args.no_external:
        allow_external = False

    seed_id = queue.add_seed(conn, args.URL, max_depth=args.max_depth, max_pages=args.max_pages,
                             allow_external=allow_external, recrawl_hours=args.recrawl_hours)
    if seed_id is None:
        print(f"bad url: {args.URL}", file=sys.stderr)
        return 2
    else:
        seed_url = db.get_seed_url(conn, seed_id)
        print(f"seed {seed_id}: {seed_url}")
        db.audit(conn, "cli", "seed_add", seed_url)
        return 0

def cmd_seed_list(conn, args):
    seeds = db.get_seeds(conn)
    for seed in seeds:
        id, url, enabled, max_depth, max_pages, external, total_urls, done_urls = seed
        enabled_str = "on" if enabled else "off"
        max_depth_str = str(max_depth) if max_depth is not None else "-"
        max_pages_str = str(max_pages) if max_pages is not None else "-"
        external_str = "yes" if external == 1 else "no" if external == 0 else "-"
        print(f"{id}\t{url}\t{enabled_str}\t{max_depth_str}\t{max_pages_str}\t{external_str}\t{total_urls}\t{done_urls}")
    return 0

def _fmt(value):
    return str(value).lower() if isinstance(value, bool) else str(value)

def cmd_config(conn, args):
    if args.KEY is None:
        settings = db.get_settings(conn)
        for key, value in sorted(settings.items()):
            print(f"{key} = {_fmt(value)}")
        return 0
    if args.KEY not in db.DEFAULT_SETTINGS:
        print(f"unknown setting: {args.KEY}", file=sys.stderr)
        return 2
    elif args.VALUE is None:
        value = db.get_setting(conn, args.KEY)
        if value is None:
            print(f"unknown setting: {args.KEY}", file=sys.stderr)
            return 2
        else:
            print(_fmt(value))
            return 0
    else:
        try:
            value = db.convert_setting_value(args.KEY, args.VALUE)
        except ValueError:
            print(f"bad value for {args.KEY}: {args.VALUE}", file=sys.stderr)
            return 2
        else:
            db.set_setting(conn, args.KEY, value)
            db.audit(conn, "cli", "set_setting", f"{args.KEY}={value}")
            print(f"{args.KEY} = {_fmt(value)}")
            return 0

def cmd_status(conn, args):
    stats = db.get_stats(conn)
    print(f"state: {stats['crawl_state']}")
    print(f"urls: {stats['total_urls']} total, {stats['domains']} domains")
    for status, count in sorted(stats['by_status'].items()):
        print(f"  {status}: {count}")
    print(f"errors last hour: {stats['errors_last_hour']}")
    print(f"robots.txt: {'respected' if stats['respect_robots'] else 'IGNORED'}")
    return 0

def cmd_run(conn, args):
    overrides = {}
    if args.concurrency is not None:
        overrides['concurrency'] = args.concurrency
    if args.delay is not None:
        overrides['default_delay'] = args.delay
    if args.ignore_robots:
        overrides['respect_robots'] = False
    elif args.respect_robots:
        overrides['respect_robots'] = True

    if overrides:
        for key, value in overrides.items():
            db.set_setting(conn, key, value)
        db.audit(conn, "cli", "run_options", ', '.join(f"{k}={v}" for k, v in overrides.items()))

    respect = db.get_settings(conn)["respect_robots"]
    print(f"robots.txt: {'respected' if respect else 'IGNORED'}")
    conn.close()
    Crawler(args.db).run(exit_when_idle=not args.forever)
    print("done")
    return 0

def cmd_control(conn, args):
    if args.command == 'pause':
        crawler.pause(conn)
        db.audit(conn, "cli", "pause")
        print("crawl_state: paused")
    elif args.command == 'resume':
        crawler.resume(conn)
        db.audit(conn, "cli", "resume")
        print("crawl_state: running")
    elif args.command == 'stop':
        crawler.request_stop(conn)
        db.audit(conn, "cli", "stop")
        print("crawl_state: stopped")
    return 0

def _host_arg(domain):
    d = domain.strip().lower()
    return host_of(d) if "://" in d else d

def cmd_block(conn, args):
    host = _host_arg(args.DOMAIN)
    db.block_domain(conn, host)
    db.audit(conn, "cli", "block", host)
    print(f"blocked {host}")
    return 0

def cmd_unblock(conn, args):
    host = _host_arg(args.DOMAIN)
    db.unblock_domain(conn, host)
    db.audit(conn, "cli", "unblock", host)
    print(f"unblocked {host}")
    return 0

def cmd_retry_errors(conn, args):
    count = db.retry_errors(conn)
    print(f"requeued {count}")
    db.audit(conn, "cli", "retry_errors", f"requeued {count}")
    return 0

EXPORT_COLUMNS = ["url", "host", "status", "http_status", "title", "description", "content_type", "depth", "fetched_at"]

def cmd_export(conn, args):
    rows = db.get_urls(conn, status=args.status)
    out = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
    try:
        if args.format == "csv":
            writer = csv.writer(out)
            writer.writerow(EXPORT_COLUMNS)
            writer.writerows(rows)
        else:
            json.dump([dict(zip(EXPORT_COLUMNS, r)) for r in rows], out, indent=2, ensure_ascii=False)
    finally:
        if args.out:
            out.close()
    return 0

def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)

    conn = db.connect(args.db)
    try:
        if args.command == 'seed':
            if args.subcommand == 'add':
                return cmd_seed_add(conn, args)
            elif args.subcommand == 'list':
                return cmd_seed_list(conn, args)
        elif args.command == 'config':
            return cmd_config(conn, args)
        elif args.command == 'status':
            return cmd_status(conn, args)
        elif args.command == 'run':
            return cmd_run(conn, args)
        elif args.command in ['pause', 'resume', 'stop']:
            return cmd_control(conn, args)
        elif args.command == 'block':
            return cmd_block(conn, args)
        elif args.command == 'unblock':
            return cmd_unblock(conn, args)
        elif args.command == 'retry-errors':
            return cmd_retry_errors(conn, args)
        elif args.command == 'export':
            return cmd_export(conn, args)
    finally:
        conn.close()

    return 0
