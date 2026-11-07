# Spider

A polite web crawler with a command line tool and a password-protected web
admin. The crawler core uses only the Python standard library; the admin needs
Flask. All state lives in one SQLite file, so the crawler can be stopped,
resumed, backed up and queried with plain `sqlite3`.

- Per-host request delay, `robots.txt` support, size / depth / page limits
- `robots.txt` handling can be switched off (setting `respect_robots`)
- Resumable: the queue is stored in the database
- Retries with backoff for timeouts, connection errors, 5xx and 429
- Recrawl schedule per seed (`--recrawl-hours`)
- Block lists, per-domain delay overrides, hide / approve / tag pages
- Admin: dashboard, settings, seeds, URL browser, domains, errors, logs,
  audit log, CSV / JSON export
- Every change made from the CLI or the admin is written to an audit table

Requires Python 3.10 or newer. Tested on 3.14.

## Quick start

```sh
pip install flask            # only needed for the web admin

./spider seed add https://example.com --max-depth 2 --max-pages 200
./spider run                 # crawls until the queue is empty
./spider status
./spider export --format csv --out pages.csv
```

The database is `spider.db` in the current directory. Use `--db PATH` before
the command, or set `SPIDER_DB`, to put it somewhere else:

```sh
./spider --db /srv/spider/spider.db status
SPIDER_DB=/srv/spider/spider.db ./spider status
```

## Command line

| Command | What it does |
|---|---|
| `seed add URL [--max-depth N] [--max-pages N] [--external \| --no-external] [--recrawl-hours N]` | Add a starting point. Blank limits use the global settings. |
| `seed list` | One line per seed: id, url, on/off, depth, pages, external, total URLs, done URLs |
| `run [--concurrency N] [--delay S] [--ignore-robots \| --respect-robots] [--forever]` | Crawl. Stops when the queue is empty unless `--forever`. |
| `pause` / `resume` / `stop` | Control a running crawl (workers check every few seconds) |
| `status` | Crawl state, URL counts by status, errors in the last hour, robots.txt on/off |
| `config [KEY [VALUE]]` | List, read or change a setting |
| `block DOMAIN` / `unblock DOMAIN` | Never fetch a host (and its subdomains) |
| `retry-errors` | Put every errored URL back in the queue |
| `export [--format csv\|json] [--status S] [--out FILE]` | Dump URLs |
| `schedule [--run]` | Show when each seed is due for a recrawl, or requeue what is due now |
| `serve [--host H] [--port P] [--password PW] [--trust-proxy]` | Run the web admin |

Examples:

```sh
./spider config                         # all settings
./spider config default_delay 5         # wait 5 s between requests to one host
./spider config respect_robots false    # ignore robots.txt (also shown in status)
./spider run --concurrency 8 --delay 1 --forever
./spider block spam.example
./spider export --status error --format json
```

### Settings

| Setting | Default | Meaning |
|---|---|---|
| `user_agent` | `SpiderBot/1.0 (+https://github.com/rubbermetal/Spider)` | Sent with every request. Put a contact URL in it. |
| `respect_robots` | `true` | `false` ignores robots.txt completely |
| `default_delay` | `2.0` | Seconds between requests to one host (a larger robots.txt `Crawl-delay` wins; a per-domain override beats both) |
| `concurrency` | `4` | Worker threads |
| `timeout` | `15.0` | Seconds before a request is abandoned |
| `max_bytes` | `2000000` | Larger pages are cut off |
| `max_depth` | `3` | Link depth from the seed (a seed can override it) |
| `max_pages_per_domain` | `500` | URLs queued per host |
| `allow_external` | `false` | Follow links to other sites (a seed can override it) |
| `max_retries` / `retry_backoff_seconds` | `2` / `300` | Retry transient failures after attempt x backoff seconds |

Workers re-read settings continuously, so changes apply to a running crawl
within seconds.

### How scope works

A link is queued only if it passes, in this order: it is a normal http(s) URL,
it is not an image / archive / media file, it is within the seed's depth, its
domain is not blocked, it stays on the seed's site (unless external links are
allowed), and the seed and host page limits are not reached. A redirect that
leaves the seed's site (when external links are off) or lands on a blocked
domain marks the URL `skipped`. Pages with
`<meta name="robots" content="noindex">` are hidden automatically; `nofollow`
pages do not contribute links.

## Recrawl schedule

Give a seed an interval and it is crawled again when due:

```sh
./spider seed add https://example.com --recrawl-hours 24
./spider schedule              # id, url, interval, last recrawl, next due
./spider run --forever         # checks for due seeds about every 30 s while idle
./spider schedule --run        # requeue whatever is due right now
```

A one-shot `./spider run` never starts recrawls; use `--forever` (or the
"keep running" box on the dashboard). A seed whose crawl is still in progress
is skipped until it finishes.

## Web admin

```sh
export SPIDER_ADMIN_PASSWORD='choose-a-long-password'
./spider serve --host 127.0.0.1 --port 8080
```

Prefer the environment variable to `--password`, which shows up in `ps`.
Without a password every page answers 503.

| Page | Use |
|---|---|
| Dashboard | Live counts, pages per minute, robots on/off, Start / Pause / Resume / Stop, recent log |
| URLs | Filter by status / host / text / tag / seed, sort, page, bulk requeue / hide / approve / tag / delete |
| Seeds | Add, edit limits, enable / disable, recrawl now, delete; shows next recrawl |
| Domains | Per-host counts, block, delay override, notes, cached robots.txt with refetch |
| Errors | Failures grouped by kind (timeout, DNS, SSL, each HTTP code, robots blocks ...), retry a group |
| Logs / Audit | Event log (prunable) and the audit trail (never pruned) |
| Export | CSV or JSON; "approved only, hidden excluded" is the list to publish |
| Settings | Every setting above, validated, with a warning when robots.txt is ignored |

Security: password login, a CSRF token on every POST, five failed logins in
five minutes lock that address out (HTTP 429), session cookies are HttpOnly
and SameSite=Lax. Behind a reverse proxy pass `--trust-proxy` and make the
proxy set `X-Real-IP` itself, replacing any client-supplied value (see
`deploy/Caddyfile.example`).

The crawler started from the admin runs as a thread inside the admin process,
so **run exactly one worker process** (the unit file below does). A crawl
started with `spider run` in another process works too: both read and write
the same database, and Pause / Stop from either side reach both.

## Deploying on a server

`deploy/spider-admin.service` and `deploy/Caddyfile.example` show a systemd
unit (gunicorn, one worker, 8 threads) and a Caddy site that proxies to it:

```sh
sudo useradd --system --home /opt/spider spider
sudo mkdir -p /opt/spider/data && sudo cp -r spider spiderlib deploy requirements.txt /opt/spider/
cd /opt/spider && sudo python3 -m venv venv && sudo venv/bin/pip install -r requirements.txt gunicorn
sudo sh -c 'umask 077; printf "SPIDER_ADMIN_PASSWORD=...\nSPIDER_SECRET=...\n" > /opt/spider/.env'
sudo chown -R spider:spider /opt/spider
sudo cp deploy/spider-admin.service /etc/systemd/system/ && sudo systemctl enable --now spider-admin
```

Set `SPIDER_SECRET` to a long random string so logins survive restarts.
Back the database up with `sqlite3 data/spider.db ".backup backup.db"`.

## Data

Tables: `settings`, `seeds`, `urls` (queue and results in one table), `links`,
`domains`, `log`, `audit`. URL statuses: `queued`, `fetching`, `done`,
`error`, `blocked`, `skipped`.

```sh
sqlite3 spider.db "select status, count(*) from urls group by status"
sqlite3 spider.db "select url, title from urls where status='done' and approved=1"
```

## Tests

```sh
python3 -m pytest -q
```

Covers URL handling, robots.txt, parsing, the fetcher (against a local HTTP
server), the queue and scope rules, the engine (with a fake site), the CLI and
every admin page.

## Layout

```
spider                 launcher (python3 spider ...)
spiderlib/             urls, db, robots, parse, fetch, queue, crawler, schedule, cli, serve
spiderlib/admin/       Flask app: auth, dashboard, settings, seeds, urls, domains,
                       errors, logs, export (+ templates/, static/)
tests/                 pytest suite
deploy/                systemd unit and Caddy example
PLAN-admin.md          how the admin was planned and built
```
