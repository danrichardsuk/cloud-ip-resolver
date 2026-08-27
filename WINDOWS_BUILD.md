# Windows executable build and distribution

Cloud IP Resolver is packaged as a single Windows GUI executable with PyInstaller. The finished file is `dist\CloudIPResolver.exe` and does not require the end user to install Python.

## Why the build must run on Windows

PyInstaller packages against the operating system it is running on; it is not a cross-compiler. Local builds therefore run on Windows, and the automated build uses GitHub's `windows-latest` runner.

## Local build

From the repository root, activate the project virtual environment and run:

```powershell
C:\Users\dan.richards\.venvs\cloud-ip-resolver\Scripts\Activate.ps1
.\scripts\build_windows.ps1
```

The build script:

1. installs/updates the project development dependencies, including PyInstaller
2. runs the full pytest suite
3. cleans old PyInstaller build output
4. builds a one-file Windows GUI executable with no console window
5. verifies that `dist\CloudIPResolver.exe` was created and reports its size

For a packaging-only rebuild after tests have already passed:

```powershell
.\scripts\build_windows.ps1 -SkipTests
```

## Automated GitHub build

`.github\workflows\windows-build.yml` runs on every push to `main`, on `v*` version tags and when started manually from GitHub Actions.

The workflow uses Python 3.13 on a clean Windows runner, calls the same `scripts\build_windows.ps1` used locally, creates a SHA-256 checksum, and uploads both files as a workflow artifact:

```text
CloudIPResolver.exe
CloudIPResolver.exe.sha256
```

Main-branch workflow artifacts are retained for 30 days and are intended for development/testing.

When the workflow is triggered by a version tag such as `v0.8.0`, it additionally checks that the tag matches the Python application version and publishes the EXE/checksum as GitHub Release assets. See `RELEASES.md` for the release procedure and download model.

## What is tracked in Git

- `CloudIPResolver.spec` — PyInstaller one-file/windowed build recipe
- `packaging\windows_launcher.py` — tiny executable entry point that calls the tested desktop GUI
- `packaging\windows_version_info.txt` — Windows Explorer product/version metadata
- `scripts\build_windows.ps1` — repeatable local Windows build command
- `.github\workflows\windows-build.yml` — clean Windows CI build and release automation
- `tests\test_packaging.py` — executable packaging regression checks
- `tests\test_github_actions.py` — CI/release contract checks

Generated `build\` and `dist\` folders remain ignored by Git.

## Validate the EXE

After a successful local build, double-click:

```text
dist\CloudIPResolver.exe
```

Then perform a normal real-data run with AWS, Azure and Google Cloud selected. Check that:

- the app starts without a console window
- provider downloads complete successfully
- the output CSV is created
- match counts agree with the Python GUI
- `Open Output Folder` works
- the progress/timer behaviour remains responsive

For the strongest no-Python validation, copy only `CloudIPResolver.exe` to another Windows machine or test account that does not have the project environment on its PATH.

## Windows security note

Current builds are unsigned. Windows Defender/SmartScreen or corporate endpoint protection may therefore inspect or warn about the executable. Code signing is a later release-hardening step and is separate from whether the PyInstaller package itself works correctly.
