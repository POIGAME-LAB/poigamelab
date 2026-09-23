"""Run from repository: python -m pytest proposals/test_readonly_runner.py.
The proposal runner must be beside this test. No network requests are made.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path.cwd() / "scripts"))


@pytest.mark.parametrize("fail", [False, True])
def test_writes_and_failures_are_confined_to_temporary_copy(tmp_path, monkeypatch, fail):
    spec = importlib.util.spec_from_file_location("audit_runner", Path(__file__).resolve().parents[1] / "scripts/audit_readonly_scan.py")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    repo = tmp_path / "repo"
    (repo / "data").mkdir(parents=True)
    (repo / "config").mkdir()
    (repo / "games.csv").write_text("original-games")
    (repo / "data/published_offers.csv").write_text("original-offers")
    monkeypatch.setattr(runner, "ROOT", repo)
    monkeypatch.setattr(runner.direct, "ROOT", repo)
    monkeypatch.setattr(runner.direct, "PUBLISHED", repo / "data/published_offers.csv")

    def collector(after_scan):
        assert runner.direct.PUBLISHED != repo / "data/published_offers.csv"
        runner.direct.PUBLISHED.write_text("simulated-collector-write")
        if fail:
            raise RuntimeError("fetch failed")
        return 0

    monkeypatch.setattr(runner.direct, "main", collector)
    output = tmp_path / "result.json"
    if fail:
        with pytest.raises(RuntimeError, match="fetch failed"):
            runner.run(output)
    else:
        assert runner.run(output) == 0
        result = json.loads(output.read_text())
        assert result["publicationAuthorized"] is False
        assert result["protectedFilesUnchanged"] is True
    assert (repo / "games.csv").read_text() == "original-games"
    assert (repo / "data/published_offers.csv").read_text() == "original-offers"
