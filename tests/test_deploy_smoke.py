import importlib.util
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_public_site",
    ROOT / "scripts" / "build_public_site.py",
)
builder = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(builder)


def test_deploy_artifact_contains_core_public_files():
    output = ROOT / ".test-deploy-site"
    if output.exists():
        shutil.rmtree(output)
    try:
        copied = set(builder.build_public_site(output))
        required = {
            "index.html",
            "game.html",
            "guides.html",
            "offers.html",
            "robots.txt",
            "sitemap.xml",
            "CNAME",
            "site-data.js",
            "site-footer.js",
            "data/published_offers.csv",
            "data/new_game_monitor.json",
            "data/existing_game_monitor.json",
            "config/refresh_policy.json",
        }
        assert required <= copied
        assert (output / "sitemap.xml").read_text(encoding="utf-8").startswith("<?xml")
        assert "https://poigamelab.com/" in (output / "sitemap.xml").read_text(encoding="utf-8")
        assert (output / "CNAME").read_text(encoding="utf-8").strip() == "poigamelab.com"
        assert "Sitemap: https://poigamelab.com/sitemap.xml" in (output / "robots.txt").read_text(encoding="utf-8")
    finally:
        if output.exists():
            shutil.rmtree(output)
