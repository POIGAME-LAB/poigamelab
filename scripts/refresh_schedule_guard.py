#!/usr/bin/env python3
"""Decide whether the backup trigger should start the daily offer refresh (no network, no API).

GitHub sometimes drops a scheduled run: on 2026-11-24 JST the 16:17 UTC run of
``refresh-verified-offers.yml`` was never created, so the site and the 12:07 daily-guide routine
had only the previous day's data. The backup workflow runs this guard late in the JST morning and
starts the refresh with ``workflow_dispatch`` only when **both** are true:

* ``data/refresh_status.json`` on main was not written by a run that started today (JST), and
* no run of the refresh workflow was created today (JST) in any state - a queued, running or
  failed run is left alone (a failure needs a person, not a blind retry).

    gh run list --workflow refresh-verified-offers.yml --json createdAt,status,conclusion \\
        | python scripts/refresh_schedule_guard.py --status data/refresh_status.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))


def _jst_date(value):
    try:
        moment = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if moment.tzinfo is None:
        return None
    return moment.astimezone(JST).date()


def decide(status: dict | None, runs: list | None, now: datetime) -> tuple[bool, str]:
    today = now.astimezone(JST).date()
    started = _jst_date((status or {}).get("startedAt"))
    if started == today:
        return False, "already_refreshed_today"
    if not isinstance(runs, list):
        return False, "run_list_unavailable"  # fail closed: never start a refresh blind
    for run in runs:
        if isinstance(run, dict) and _jst_date(run.get("createdAt")) == today:
            return False, f"refresh_run_exists_today:{run.get('status')}:{run.get('conclusion') or ''}"
    return True, "no_refresh_today"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--status", default="data/refresh_status.json")
    ap.add_argument("--runs", help="JSON file from gh run list (default: stdin)")
    args = ap.parse_args(argv)
    try:
        status = json.loads(Path(args.status).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        status = None
    try:
        raw = Path(args.runs).read_text(encoding="utf-8") if args.runs else sys.stdin.read()
        runs = json.loads(raw)
    except (OSError, ValueError):
        runs = None
    run, reason = decide(status, runs, datetime.now(timezone.utc))
    print(f"backup refresh: run={str(run).lower()} reason={reason}")
    out = os.environ.get("GITHUB_OUTPUT")
    if out:
        with open(out, "a", encoding="utf-8") as handle:
            handle.write(f"run={str(run).lower()}\nreason={reason}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
