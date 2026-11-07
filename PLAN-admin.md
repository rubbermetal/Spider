# Spider admin: plan

Status (2026-11-07): stages A to I are done; see README.md for usage.

Web admin for the crawler, Flask, password-protected, served by `spider serve`.
All state lives in the SQLite database, so the admin and the CLI (`spider run`)
can be used together. No CDN assets: CSS and JS are local files.

Rule for building it: **small modules** (each file about 150 lines or less) so a
local model can write or fix one in a single pass. Query code lives in plain
modules (testable without Flask); views stay thin.

## Layout

    spiderlib/admin/
      __init__.py     create_app(db_path, password, ...)
      dbconn.py       per-request sqlite connection (flask.g)
      auth.py         login/logout, CSRF, lockout, request guard
      runner.py       starts/tracks the in-process crawler thread
      dashboard.py    dashboard page, /api/stats, crawl control buttons
      settings.py     settings form
      seeds.py        seeds: add, edit limits, enable/disable, recrawl now
      urls.py         queue + pages browser, detail, single and bulk actions
      domains.py      per-host stats, block, delay override, robots viewer
      errors.py       errors grouped by kind, retry
      logs.py         event log and audit log viewers
      queries_*.py    SQL for the views above
      templates/      base.html + one template per page
      static/         admin.css, admin.js

## Stages

A. skeleton, login (CSRF, lockout), runner, dashboard with live stats, crawl control
B. settings form (typed fields, audit)
C. seeds
D. URL browser (filters, search, pagination, detail, bulk actions, hide/approve/tags)
E. domains
F. errors
G. logs and audit viewers, export download
H. scheduler: recrawl seeds by `recrawl_hours`
I. README, deploy notes (single worker: the crawler runs inside the admin process)

## Decisions

- Password from `SPIDER_ADMIN_PASSWORD` (or `--password`); unset means every page
  answers 503 (same convention as the building suite).
- 5 failed logins in 300 s from one address means 429.
- Every POST needs a CSRF token; every admin change is written to the audit table
  with actor `admin`.
- The crawler thread is started by the admin (`Runner`), so run one worker process.
  Control (pause/resume/stop) is by the `crawl_state` setting, same as the CLI.
- Admin never deletes without a confirm step in the UI; deleting a URL row also
  deletes its link rows.
