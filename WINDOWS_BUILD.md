# Local Windows executable build

Cloud IP Resolver can be packaged as a single Windows GUI executable with PyInstaller. The finished file is `dist\CloudIPResolver.exe` and does not require the end user to install Python.

## Why the build must run on Windows

PyInstaller packages against the operating system it is running on; it is not a cross-compiler. Build `CloudIPResolver.exe` on Windows using the same 64-bit Python environment used for development.

## Build

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

## What is tracked in Git

- `CloudIPResolver.spec` — PyInstaller one-file/windowed build recipe
- `packaging\windows_launcher.py` — tiny executable entry point that calls the tested desktop GUI
- `packaging\windows_version_info.txt` — Windows Explorer product/version metadata
- `scripts\build_windows.ps1` — repeatable local Windows build command
- `tests\test_packaging.py` — regression checks for executable name, no-console mode and version metadata

Generated `build\` and `dist\` folders remain ignored by Git.

## Validate the EXE

After a successful build, double-click:

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

The first local build is unsigned. Windows Defender/SmartScreen or corporate endpoint protection may therefore inspect or warn about the executable. Code signing is a later release-hardening step and is separate from whether the PyInstaller package itself works correctly.
