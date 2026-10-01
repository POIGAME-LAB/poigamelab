"""robots.txt lets crawlers read only the data files the public pages render."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_public_site as build  # noqa: E402


def rules():
    out = []
    for line in (ROOT / "robots.txt").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition(":")
        if key.strip() in {"Allow", "Disallow"}:
            out.append((key.strip(), value.strip()))
    return out


def allowed(path):
    """Google's rule: the longest matching path wins; Allow wins a tie."""
    matches = [(len(p), kind == "Allow") for kind, p in rules() if path.startswith(p)]
    return max(matches)[1] if matches else True


def test_rendered_public_data_is_crawlable():
    for name in build.DATA_FILES:
        if name != "exception_queue.json":  # only the noindex data-status page reads it
            assert allowed(f"/data/{name}"), name
    for name in build.CONFIG_FILES:
        assert allowed(f"/config/{name}"), name
    for name in build.DATA_DIRS:
        assert allowed(f"/data/{name}/township.json"), name


def test_every_allowed_data_path_is_published_by_the_build():
    public = ({f"/data/{n}" for n in build.DATA_FILES}
              | {f"/config/{n}" for n in build.CONFIG_FILES}
              | {f"/data/{d}/" for d in build.DATA_DIRS})
    for kind, path in rules():
        if kind == "Allow" and path.startswith(("/data/", "/config/")):
            assert path in public, path


def test_internal_paths_stay_blocked():
    for path in ("/data/daily_scan_review.json", "/data/verified_offer_urls.json",
                 "/data/offer_unavailable_runs.json", "/data/exception_queue.json",
                 "/config/game_targets.json", "/scripts/x.py", "/data-status.html"):
        assert not allowed(path), path
    assert allowed("/") and allowed("/township-lv70.html")
