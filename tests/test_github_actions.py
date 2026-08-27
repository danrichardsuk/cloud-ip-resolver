"""Regression tests for the GitHub Actions Windows build/release workflow.

These tests deliberately inspect the workflow as text rather than executing
GitHub Actions. They protect the important delivery contracts without adding a
YAML parser dependency to the project.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "windows-build.yml"


def _workflow_text() -> str:
    """Return the tracked Windows workflow text for delivery-contract tests."""

    return WORKFLOW.read_text(encoding="utf-8")


def test_windows_workflow_builds_and_uploads_executable() -> None:
    """Ensure main-branch CI uses Windows and exposes the packaged EXE."""

    workflow = _workflow_text()

    assert "runs-on: windows-latest" in workflow
    assert ".\\scripts\\build_windows.ps1" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "dist/CloudIPResolver.exe" in workflow
    assert "retention-days: 30" in workflow


def test_version_tags_publish_github_release_assets() -> None:
    """Ensure version-tag builds create durable release downloads."""

    workflow = _workflow_text()

    assert 'tags:\n      - "v*"' in workflow
    assert "gh release create" in workflow
    assert "gh release upload" in workflow
    assert "CloudIPResolver.exe.sha256" in workflow
    assert "contents: write" in workflow


def test_release_workflow_guards_tag_and_application_version() -> None:
    """Prevent a tag from publishing an EXE whose embedded app version differs."""

    workflow = _workflow_text()

    assert "cloud_ip_resolver.__version__" in workflow
    assert "$env:TAG_NAME.TrimStart(\"v\")" in workflow
    assert "does not match application version" in workflow
