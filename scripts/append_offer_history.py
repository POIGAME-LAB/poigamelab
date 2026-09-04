#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published_offers.csv"
HISTORY = ROOT / "data" / "offer_history.csv"

FIELDS = ("observedAt", "game", "site", "platform", "reward", "offerKey")


def read_csv(path: Path):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def canonical_groups(rows):
    grouped = {}
    for row in rows:
        if str(row.get("verified") or "").strip().lower() != "true":
            continue
        game = str(row.get("game") or "").strip()
        site = str(row.get("site") or "").strip()
        platform = str(row.get("platform") or "").strip() or "不明"
        reward_raw = str(row.get("reward") or "").strip()
        if not game or not site or not reward_raw.isdigit():
            continue
        reward = int(reward_raw)
        key = (game, site, platform)
        current = grouped.get(key)
        if current is None or reward > current["reward"]:
            grouped[key] = {
                "game": game,
                "site": site,
                "platform": platform,
                "reward": reward,
                "offerKey": str(row.get("offerKey") or "").strip(),
            }
    return [grouped[key] for key in sorted(grouped)]


def history_snapshots(rows):
    snapshots = {}
    for row in rows:
        observed_at = str(row.get("observedAt") or "").strip()
        game = str(row.get("game") or "").strip()
        site = str(row.get("site") or "").strip()
        platform = str(row.get("platform") or "").strip() or "不明"
        reward_raw = str(row.get("reward") or "").strip()
        if not observed_at or not game or not site or not reward_raw.isdigit():
            continue
        snapshots.setdefault(observed_at, []).append(
            (game, site, platform, int(reward_raw))
        )
    return snapshots


def current_state(groups):
    return tuple(
        (item["game"], item["site"], item["platform"], int(item["reward"]))
        for item in groups
    )


def append_snapshot(published_path=PUBLISHED, history_path=HISTORY, observed_at=None):
    published_rows = read_csv(published_path)
    groups = canonical_groups(published_rows)
    if not groups:
        return {"appended": False, "reason": "no_verified_groups", "groupCount": 0}

    history_rows = read_csv(history_path)
    snapshots = history_snapshots(history_rows)
    latest_state = None
    if snapshots:
        latest_time = max(snapshots)
        latest_state = tuple(sorted(snapshots[latest_time]))

    state = current_state(groups)
    if latest_state == state:
        return {"appended": False, "reason": "unchanged", "groupCount": len(groups)}

    observed_at = observed_at or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    write_header = not history_path.exists() or history_path.stat().st_size == 0
    history_path.parent.mkdir(parents=True, exist_ok=True)
    with history_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        if write_header:
            writer.writeheader()
        for item in groups:
            writer.writerow({
                "observedAt": observed_at,
                "game": item["game"],
                "site": item["site"],
                "platform": item["platform"],
                "reward": item["reward"],
                "offerKey": item["offerKey"],
            })
    return {"appended": True, "reason": "changed", "groupCount": len(groups), "observedAt": observed_at}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="Append a reward snapshot when verified group values changed.")
    parser.add_argument("--observed-at", default=None)
    parser.add_argument("--published", type=Path, default=PUBLISHED)
    parser.add_argument("--history", type=Path, default=HISTORY)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    result = append_snapshot(args.published, args.history, args.observed_at)
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
