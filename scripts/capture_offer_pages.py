#!/usr/bin/env python3
"""Save the first-party pages the daily refresh cannot read, so parsers can be fixed offline.

The 2026-11-24 daily log (SOURCE_DIAGNOSTICS / PUBLICATION_HOLDS) showed why offers are held,
but the pages themselves cannot be fetched from the editing environment. This script runs in a
manual GitHub Actions job, fetches a bounded set of registered first-party pages with the same
``fetch_first_party`` the daily refresh uses, and writes them plus parser results to a folder that
is uploaded as a short-lived artifact. It never writes repository data, never publishes, uses no
API keys and no secrets.

Pages captured (each URL once, politely spaced, at most --max-pages):
* every known detail URL in config/game_targets.json for the requested sources;
* the configured listing / start URLs of the requested sources (to see Nifty's 404 and
  Kurashiru's 402 responses as they are).
"""
from __future__ import annotations

import argparse
import base64
import gzip
import hashlib
import json
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import direct_offer_refresh as direct  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCES = ("hapitas", "moppy", "warau", "amefuri", "point_town", "nifty_point", "kurashiru_reward")
MAX_PAGES = 120


def plan(sources_cfg: dict, targets: list, wanted: tuple, max_pages: int = MAX_PAGES) -> list[dict]:
    """(source, url, kind, game) to fetch: registered hosts only, de-duplicated, bounded."""
    out, seen = [], set()

    def add(sid, url, kind, game=""):
        source = sources_cfg.get(sid)
        if not source or not isinstance(url, str) or not url.startswith("https://"):
            return
        if not direct.source_host_allowed(url, source) or (sid, url) in seen:
            return
        seen.add((sid, url))
        out.append({"source": sid, "url": url, "kind": kind, "game": game})

    for sid in wanted:
        source = sources_cfg.get(sid) or {}
        for url in [source.get("start_url"), *(source.get("direct_listing_urls") or [])][:3]:
            add(sid, url, "listing")
    for target in targets:
        for sid, urls in (target.get("known_urls_by_source") or {}).items():
            if sid in wanted:
                for url in urls or []:
                    add(sid, url, "detail", str(target.get("game") or ""))
    return out[:max(0, min(int(max_pages), MAX_PAGES))]


def _error_code(error) -> str:
    return direct.summarize_fetch_error(error) if isinstance(error, BaseException) else "error"


def capture(items: list[dict], out_dir: Path, sources_cfg: dict, aliases_by_game: dict, fetcher=None, delay=1.0) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    fetch = fetcher or (lambda url, source: direct.fetch_first_party(url, source))
    index = []
    for n, item in enumerate(items, 1):
        if n > 1 and delay:
            time.sleep(delay)
        entry = dict(item)
        source = sources_cfg[item["source"]]
        try:
            raw, final_url = fetch(item["url"], source)
        except HTTPError as error:
            body = b""
            try:
                body = error.read(200_000) or b""
            except Exception:
                pass
            entry.update(status=_error_code(error), bytes=len(body))
            if body:
                name = f"{n:03d}_{item['source']}_error.html"
                (out_dir / name).write_bytes(body)
                entry["file"] = name
            index.append(entry)
            continue
        except Exception as error:  # network/timeouts: record the category only
            entry.update(status=_error_code(error))
            index.append(entry)
            continue
        text = raw if isinstance(raw, str) else str(raw)
        name = f"{n:03d}_{item['source']}_{item['kind']}.html"
        (out_dir / name).write_text(text, encoding="utf-8")
        entry.update(status="ok", file=name, finalUrl=final_url, bytes=len(text.encode("utf-8")),
                     sha256=hashlib.sha256(text.encode("utf-8")).hexdigest())
        if item["kind"] == "detail":
            try:
                aliases = aliases_by_game.get(item["game"]) or [item["game"]]
                detail = direct.inspect_detail(item["url"], source, aliases, fetcher=lambda u, s: (raw, final_url))
                ev = detail.get("sourceEvidence") or {}
                entry["parser"] = {"state": ev.get("state"), "reason": ev.get("reason"),
                                   "parserVersion": ev.get("parserVersion"), "platform": ev.get("platform")}
            except Exception as error:
                entry["parser"] = {"state": "exception", "reason": type(error).__name__}
        index.append(entry)
    (out_dir / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return index


def emit_pages(index: list[dict], out_dir: Path, write=print, width: int = 900) -> int:
    """Print saved pages into the job log as gzip+base64 lines (PAGE_BEGIN / PAGEDATA / PAGE_END).

    Artifacts are stored on a blob host the editing environment cannot reach, while job logs can
    be read through the GitHub API. The pages are public first-party pages; nothing else is printed.
    """
    count = 0
    for entry in index:
        name = entry.get("file")
        if not name:
            continue
        data = base64.b64encode(gzip.compress((out_dir / name).read_bytes(), 9)).decode("ascii")
        chunks = [data[i:i + width] for i in range(0, len(data), width)] or [""]
        write(f"PAGE_BEGIN {name} {len(chunks)}")
        for chunk in chunks:
            write(f"PAGEDATA {name} {chunk}")
        write(f"PAGE_END {name}")
        count += 1
    return count


def decode_log(lines) -> dict:
    """Inverse of emit_pages for a downloaded log (timestamps before the marker are ignored)."""
    parts, out = {}, {}
    for line in lines:
        i = line.find("PAGEDATA ")
        if i >= 0:
            _, name, chunk = line[i:].rstrip("\n").split(" ", 2)
            parts.setdefault(name, []).append(chunk.strip())
            continue
        j = line.find("PAGE_END ")
        if j >= 0:
            name = line[j:].split(" ", 1)[1].strip()
            out[name] = gzip.decompress(base64.b64decode("".join(parts.pop(name, []))))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--sources", default=",".join(DEFAULT_SOURCES))
    ap.add_argument("--max-pages", type=int, default=80)
    ap.add_argument("--out", default="captured-pages")
    ap.add_argument("--delay", type=float, default=1.0)
    ap.add_argument("--emit-log", action="store_true", help="also print the saved pages into the job log")
    args = ap.parse_args(argv)
    sources_cfg = {s["id"]: s for s in json.loads((ROOT / "config/point_sources.json").read_text(encoding="utf-8"))["sources"]}
    targets = json.loads((ROOT / "config/game_targets.json").read_text(encoding="utf-8"))["games"]
    aliases = {t["game"]: [t["game"], *t.get("aliases", [])] for t in targets}
    wanted = tuple(s.strip() for s in args.sources.split(",") if s.strip())
    items = plan(sources_cfg, targets, wanted, args.max_pages)
    index = capture(items, Path(args.out), sources_cfg, aliases, delay=args.delay)
    summary = {}
    for e in index:
        key = f"{e['source']}:{e['kind']}:{e['status']}" + (f":{(e.get('parser') or {}).get('state')}" if e.get("parser") else "")
        summary[key] = summary.get(key, 0) + 1
    print("CAPTURE_SUMMARY " + json.dumps(dict(sorted(summary.items())), ensure_ascii=False))
    if args.emit_log:
        print("CAPTURE_INDEX " + json.dumps(index, ensure_ascii=False))
        emit_pages(index, Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
