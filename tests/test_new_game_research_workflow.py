import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "research-new-game-content.yml"


class TestNewGameResearchWorkflow(unittest.TestCase):
    def test_auto_trigger_is_explicitly_gated(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('Refresh comparison offers (API-free)', text)
        self.assertIn("vars.ENABLE_NEW_GAME_CONTENT_RESEARCH == 'true'", text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", text)

    def test_quarantine_workflow_cannot_push_production(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("permissions:\n  contents: read", text)
        self.assertNotIn("git push", text)
        self.assertNotIn("contents: write", text)
        self.assertNotIn("adopt_verified_games.py", text)
        self.assertNotIn("git commit", text)

    def test_research_build_render_offer_gate_and_archive_are_bounded(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python scripts/research_new_game_channels.py", text)
        self.assertIn("python scripts/build_new_game_content_packages.py", text)
        self.assertIn("python scripts/render_new_game_guide.py", text)
        self.assertIn("python scripts/research_top_five_offers.py", text)
        self.assertIn("top_five_adoption_candidates.json", text)
        self.assertIn("new-game-research/latest.tgz", text)
        self.assertIn("new-game-content-bundle.sha256", text)
        self.assertIn("top-five-new-game-content-bundle", text)
        self.assertIn("timeout-minutes: 60", text)


if __name__ == "__main__":
    unittest.main()
