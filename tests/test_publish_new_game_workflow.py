import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "publish-researched-new-games.yml"


class TestPublishNewGameWorkflow(unittest.TestCase):
    def test_publication_is_explicitly_gated_after_successful_research(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn('Research top-five new games (quarantine)', text)
        self.assertIn("github.event.workflow_run.conclusion == 'success'", text)
        self.assertIn("github.event.workflow_run.head_branch == 'main'", text)
        self.assertIn("vars.ENABLE_NEW_GAME_AUTO_PUBLISH == 'true'", text)

    def test_exact_research_run_artifact_is_verified(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("actions/download-artifact@v4", text)
        self.assertIn("run-id: ${{ github.event.workflow_run.id }}", text)
        self.assertIn("sha256sum -c new-game-content-bundle.sha256", text)
        self.assertIn("cmp data/new_game_content_queue.json", text)

    def test_publication_stage_has_no_external_research_api(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertNotIn("TAVILY_API_KEY", text)
        self.assertNotIn("GEMINI_API_KEY", text)
        self.assertNotIn("FIRECRAWL_API_KEY", text)
        self.assertIn("python scripts/publish_top_five_content.py", text)

    def test_private_research_artifacts_are_not_staged(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        stage = text.split("- name: Stage only compact production outputs", 1)[1].split("- name: Commit and push production changes", 1)[0]
        self.assertIn("data/generated_guides_registry.json", stage)
        self.assertIn("data/top_five_publication_status.json", stage)
        self.assertNotIn("data/new_game_content_packages", stage)
        self.assertNotIn("data/research_results", stage)
        self.assertNotIn("data/top_five_adoption_candidates.json", stage)
        self.assertIn("git diff --cached --check", stage)

    def test_stale_main_is_rejected_before_push(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("git fetch origin main", text)
        self.assertIn("git rev-parse origin/main", text)
        self.assertIn("git push origin HEAD:main", text)
        self.assertIn("group: poigamelab-production-writer", text)

    def test_empty_queue_cannot_enter_production_write_steps(self):
        text = WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("id: bundle", text)
        for name in (
            "Deterministically adopt only content-ready V29 games",
            "Build and validate the exact Pages artifact",
            "Stage only compact production outputs",
            "Commit and push production changes",
        ):
            block = text.split(f"- name: {name}", 1)[1]
            self.assertIn("if: steps.bundle.outputs.has_items == 'true'", block.split("- name:", 1)[0])
        self.assertIn("No-op publication for an empty safe queue", text)
        self.assertIn("steps.bundle.outputs.has_items != 'true'", text)


if __name__ == "__main__":
    unittest.main()
