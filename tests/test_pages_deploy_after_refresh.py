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


def test_deploy_waits_and_retries_once_when_the_artifact_is_not_yet_visible():
    steps = WORKFLOW.split('uses: actions/upload-pages-artifact@v4', 1)[1]
    assert steps.count('uses: actions/deploy-pages@v4') == 2
    assert 'continue-on-error: true' in steps
    assert "if: steps.first_deploy.outcome == 'failure'" in steps
    # The second attempt has no continue-on-error, so a real failure still fails the run.
    retry = steps.split('id: retry_deploy', 1)[1].split('- name:', 1)[0]
    assert 'continue-on-error' not in retry
    assert 'url: ${{ steps.deployment.outputs.page_url }}' in WORKFLOW
    assert 'steps.retry_deploy.outputs.page_url' in steps
