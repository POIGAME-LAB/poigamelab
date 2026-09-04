#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import io
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PUBLISHED = ROOT / "data" / "published_offers.csv"
HISTORY = ROOT / "data" / "reward_history.csv"

FIELDS = (
    "observedAt",
    "game",
    "platform",
    "bestReward",
    "bestSite",
    "offerCount",
)
PLATFORMS = ("all", "iOS", "Android", "unknown")


def parse_csv_text(text: str):
    return list(csv.DictReader(io.StringIO(text)))


def normalize_platform(raw: str) -> list[str]:
    text = str(raw or "").strip()
    if not text or text in {"不明", "unknown", "Unknown"}:
        return ["unknown"]
    values = []
    for part in text.replace("|", ",").replace("/", ",").split(","):
        value = part.strip()
        if value in {"iOS", "Android"} and value not in values:
            values.append(value)
    return values or ["unknown"]


def summarize_rows(rows):
    verified = []
    for row in rows:
        if str(row.get("verified") or "").lower() != "true":
            continue
        try:
            reward = int(str(row.get("reward") or "").replace(",", ""))
        except ValueError:
            continue
        if reward <= 0 or not str(row.get("game") or "").strip():
            continue
        item = dict(row)
        item["_reward"] = reward
        item["_platforms"] = normalize_platform(row.get("platform"))
        verified.append(item)

    games = sorted({str(row["game"]).strip() for row in verified})
    output = {}
    for game in games:
        game_rows = [row for row in verified if str(row["game"]).strip() == game]
        for platform in PLATFORMS:
            if platform == "all":
                candidates = game_rows
            elif platform == "unknown":
                candidates = [row for row in game_rows if "unknown" in row["_platforms"]]
            else:
                candidates = [row for row in game_rows if platform in row["_platforms"]]
            if not candidates:
                continue
            best = sorted(
                candidates,
                key=lambda row: (-row["_reward"], str(row.get("site") or ""), str(row.get("offerKey") or "")),
            )[0]
            output[(game, platform)] = {
                "game": game,
                "platform": platform,
                "bestReward": best["_reward"],
                "bestSite": str(best.get("site") or "").strip(),
                "offerCount": len(candidates),
            }
    return output


def append_snapshot(history, observed_at: str, summary):
    result = list(history)
    latest = {}
    for row in result:
        latest[(row["game"], row["platform"])] = row

    for key in sorted(summary):
        item = summary[key]
        previous = latest.get(key)
        signature = (
            str(item["bestReward"]),
            item["bestSite"],
            str(item["offerCount"]),
        )
        previous_signature = None if previous is None else (
            str(previous["bestReward"]),
            previous["bestSite"],
            str(previous["offerCount"]),
        )
        if signature == previous_signature:
            continue
        result.append({
            "observedAt": observed_at,
            "game": item["game"],
            "platform": item["platform"],
            "bestReward": str(item["bestReward"]),
            "bestSite": item["bestSite"],
            "offerCount": str(item["offerCount"]),
        })
        latest[key] = result[-1]
    return result


def read_history(path=HISTORY):
    if not path.exists():
        return []
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def write_history(rows, path=HISTORY):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def git_snapshots(root=ROOT):
    proc = subprocess.run(
        ["git", "log", "--format=%H%x09%cI", "--", "data/published_offers.csv"],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    entries = []
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        sha, timestamp = line.split("\t", 1)
        entries.append((sha, timestamp))
    entries.reverse()

    for sha, timestamp in entries:
        show = subprocess.run(
            ["git", "show", f"{sha}:data/published_offers.csv"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
        yield timestamp, parse_csv_text(show.stdout)


def build_backfill(root=ROOT):
    history = []
    for observed_at, rows in git_snapshots(root):
        history = append_snapshot(history, observed_at, summarize_rows(rows))
    return history


def current_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Update POIGAME LAB best-reward history.")
    parser.add_argument("--backfill-git", action="store_true", help="Rebuild history from Git snapshots first.")
    parser.add_argument("--observed-at", help="Override current observation timestamp (ISO-8601).")
    args = parser.parse_args(argv)

    history = build_backfill(ROOT) if args.backfill_git else read_history(HISTORY)
    with PUBLISHED.open(encoding="utf-8", newline="") as handle:
        current_rows = list(csv.DictReader(handle))
    history = append_snapshot(history, args.observed_at or current_iso(), summarize_rows(current_rows))
    write_history(history, HISTORY)
    print(f"reward history rows: {len(history)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
