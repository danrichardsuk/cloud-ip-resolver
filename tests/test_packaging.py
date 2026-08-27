"""Regression tests for the tracked Windows packaging configuration.

These tests do not invoke PyInstaller, so they run on Linux/macOS CI as well as
Windows. They protect the easy-to-break contracts around executable naming,
windowed mode, and version metadata. The real executable build still needs to
run on Windows because PyInstaller is platform-specific.
"""

from pathlib import Path

from cloud_ip_resolver import __version__


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_windows_version_resource_matches_package_version() -> None:
    """Keep Windows Explorer version metadata aligned with the Python package."""

    metadata = (
        PROJECT_ROOT / "packaging" / "windows_version_info.txt"
    ).read_text(encoding="utf-8")

    assert f"StringStruct('FileVersion', '{__version__}')" in metadata
    assert f"StringStruct('ProductVersion', '{__version__}')" in metadata


def test_pyinstaller_spec_is_one_file_windowed_cloud_ip_resolver() -> None:
    """Protect the product name and no-console behaviour expected by end users."""

    spec = (PROJECT_ROOT / "CloudIPResolver.spec").read_text(encoding="utf-8")

    assert 'name="CloudIPResolver"' in spec
    assert "console=False" in spec
    assert "a.binaries" in spec
    assert "a.datas" in spec
    assert "COLLECT(" not in spec


def test_windows_launcher_reuses_desktop_main() -> None:
    """Ensure packaging launches the tested GUI instead of duplicating app logic."""

    launcher = (
        PROJECT_ROOT / "packaging" / "windows_launcher.py"
    ).read_text(encoding="utf-8")

    assert "from cloud_ip_resolver.desktop import main" in launcher
    compile(launcher, "windows_launcher.py", "exec")
