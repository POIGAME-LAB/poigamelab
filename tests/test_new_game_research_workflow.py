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
        self.assertNotIn("render_new_game_guide.py", text)

    def test_research_and_r2_archive_are_bounded_handoffs(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("python scripts/research_new_game_channels.py", text)
        self.assertIn("new-game-research/latest.tgz", text)
        self.assertIn("top-five-new-game-channel-research", text)
        self.assertIn("timeout-minutes: 45", text)


if __name__ == "__main__":
    unittest.main()
