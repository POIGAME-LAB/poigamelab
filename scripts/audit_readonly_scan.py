#!/usr/bin/env python3
"""Proposed isolated audit runner. Not installed or executed in production.

Runs the actual collector against a temporary copy. No repository data writes,
publication, R2 access, secrets, API research or git operations are performed.
Parsed rewards remain parser claims, not independent verification certificates.
"""
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import direct_offer_refresh as direct
import daily_scan_review as daily


def run(output):
    protected = [ROOT / "games.csv", ROOT / "data/published_offers.csv"]
    before = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    with tempfile.TemporaryDirectory(prefix="poigame-audit-") as folder:
        root = Path(folder)
        shutil.copytree(ROOT / "config", root / "config")
        shutil.copytree(ROOT / "data", root / "data")
        shutil.copyfile(ROOT / "games.csv", root / "games.csv")
        # Redirect every module-level repository Path, including output paths.
        for module in (direct, daily):
            for name, value in list(vars(module).items()):
                if isinstance(value, Path):
                    try:
                        setattr(module, name, root / value.relative_to(ROOT))
                    except ValueError:
                        pass
        captured = {}

        def consume(**kwargs):
            kwargs.pop("review_items", None)
            kwargs.pop("publication_policy", None)
            captured.update(daily.review_scan(**kwargs))
            # No structured publication callback and no confirmation renewal.
            return {"confirmedOfferKeys": []}

        result = direct.main(after_scan=consume)
        status_path = root / "data/comparison_refresh_status.json"
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
        if captured and status.get("newGameDiscovery"):
            daily.apply_discovery_completeness(captured, status["newGameDiscovery"])
        # Export selected public facts only, never raw page bodies or credentials.
        summary = {
            "auditOnly": True, "publicationAuthorized": False,
            "independentlyVerifiedRanking": False, "collectorExitCode": result,
            "checkedAt": captured.get("checkedAt"),
            "discovery": status.get("newGameDiscovery"),
            "rankingCompleteClaim": captured.get("rankingComplete"),
            "reviewedGroups": captured.get("reviewedGroups"),
            "detailInspectionCalls": captured.get("detailInspectionCalls"),
            "parserClaims": [{k: row.get(k) for k in (
                "game", "candidateEligible", "maxObservedRewardYen",
                "verifiedRewardSourceCount", "holdReasons")}
                for row in captured.get("results", [])],
        }
    after = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in protected}
    if before != after:
        raise RuntimeError("protected_repository_data_changed")
    summary["protectedFilesUnchanged"] = True
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    return result


if __name__ == "__main__":
    raise SystemExit(run(Path(sys.argv[1]) if len(sys.argv) > 1
                         else ROOT / "audit-results/readonly-scan.json"))
