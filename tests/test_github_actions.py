"""Regression tests for the GitHub Actions build/release delivery workflows.

These tests deliberately inspect the workflows as text rather than executing
GitHub Actions. They protect the important delivery contracts without adding a
YAML parser dependency to the project.
"""

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WINDOWS_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "windows-build.yml"
NOTES_WORKFLOW = PROJECT_ROOT / ".github" / "workflows" / "sync-release-notes.yml"


def _windows_workflow_text() -> str:
    """Return the tracked Windows build/release workflow text."""

    return WINDOWS_WORKFLOW.read_text(encoding="utf-8")


def _notes_workflow_text() -> str:
    """Return the tracked release-notes synchronization workflow text."""

    return NOTES_WORKFLOW.read_text(encoding="utf-8")


def test_windows_workflow_builds_and_uploads_executable() -> None:
    """Ensure main-branch CI uses Windows and exposes the packaged EXE."""

    workflow = _windows_workflow_text()

    assert "runs-on: windows-latest" in workflow
    assert ".\\scripts\\build_windows.ps1" in workflow
    assert "actions/upload-artifact@v4" in workflow
    assert "dist/CloudIPResolver.exe" in workflow
    assert "retention-days: 30" in workflow


def test_version_tags_publish_github_release_assets() -> None:
    """Ensure version-tag builds create durable release downloads."""

    workflow = _windows_workflow_text()

    assert 'tags:\n      - "v*"' in workflow
    assert "gh release create" in workflow
    assert "gh release upload" in workflow
    assert "CloudIPResolver.exe.sha256" in workflow
    assert "contents: write" in workflow


def test_release_workflow_guards_tag_and_application_version() -> None:
    """Prevent a tag from publishing an EXE whose embedded app version differs."""

    workflow = _windows_workflow_text()

    assert "cloud_ip_resolver.__version__" in workflow
    assert "$env:TAG_NAME.TrimStart(\"v\")" in workflow
    assert "does not match application version" in workflow


def test_tagged_release_uses_curated_user_facing_notes() -> None:
    """Keep release download/use instructions attached to versioned releases."""

    workflow = _windows_workflow_text()

    assert '$NotesPath = "RELEASE_NOTES.md"' in workflow
    assert "--notes-file $NotesPath" in workflow
    assert "gh release edit" in workflow
    assert "--generate-notes" not in workflow


def test_release_notes_changes_sync_to_current_release() -> None:
    """Update an existing matching release when curated notes change on main."""

    workflow = _notes_workflow_text()

    assert '"RELEASE_NOTES.md"' in workflow
    assert "pyproject.toml" in workflow
    assert 'TAG="v${VERSION}"' in workflow
    assert "gh release edit" in workflow
    assert "--notes-file RELEASE_NOTES.md" in workflow
