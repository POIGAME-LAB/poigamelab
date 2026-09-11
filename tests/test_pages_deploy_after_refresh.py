from pathlib import Path

WORKFLOW = Path('.github/workflows/deploy-pages.yml').read_text(encoding='utf-8')


def test_pages_deploy_runs_after_refresh_workflow_completion():
    assert 'workflow_run:' in WORKFLOW
    assert '"Refresh comparison offers (API-free)"' in WORKFLOW
    assert '- completed' in WORKFLOW


def test_workflow_run_deploy_is_limited_to_successful_main_runs():
    assert "github.event.workflow_run.conclusion == 'success'" in WORKFLOW
    assert "github.event.workflow_run.head_branch == 'main'" in WORKFLOW


def test_pages_checkout_explicitly_uses_latest_main():
    checkout = WORKFLOW.split('- uses: actions/checkout@v4', 1)[1]
    assert 'ref: main' in checkout


def test_existing_push_and_manual_deploy_triggers_remain():
    assert 'workflow_dispatch:' in WORKFLOW
    assert 'push:' in WORKFLOW
    assert '- main' in WORKFLOW
