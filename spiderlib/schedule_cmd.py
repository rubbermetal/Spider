"""
spiderlib/schedule_cmd.py

Module to handle the 'schedule' sub-command of the spider command line tool.
Usage: spider schedule / spider schedule --run
"""

from spiderlib import schedule
import sys

def add_arguments(subparsers):
    p = subparsers.add_parser("schedule", help="Show the recrawl schedule, or requeue seeds that are due")
    p.add_argument("--run", action="store_true", help="requeue every seed that is due now")
    return p

def cmd_schedule(conn, args) -> int:
    if args.run:
        results = schedule.requeue_due(conn)
        if not results:
            print("nothing due")
        else:
            for seed_id, n in results:
                print(f"seed {seed_id}: requeued {n}")
        return 0

    rows = conn.execute("SELECT id, url, enabled, recrawl_hours, last_crawled, added_at FROM seeds WHERE recrawl_hours IS NOT NULL ORDER BY id").fetchall()
    if not rows:
        print("no seeds have a recrawl interval")
        return 0

    for row in rows:
        seed_id, url, enabled, recrawl_hours, last_crawled, added_at = row
        next_due = "disabled" if enabled == 0 else schedule.next_due(dict(row))
        print(f"{seed_id}\t{url}\t{recrawl_hours}h\t{last_crawled or '-'}\t{next_due}")

    return 0
