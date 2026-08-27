# GitHub Actions and releases

Cloud IP Resolver uses GitHub Actions to build the Windows executable on a clean Windows runner and make it available in two different ways.

## Development builds

Every push to `main` runs the test suite and builds `CloudIPResolver.exe`. The workflow uploads the EXE and a SHA-256 checksum as a GitHub Actions artifact.

Actions artifacts are intended for development/testing. They are retained for 30 days by this workflow and are downloaded from the relevant workflow run.

## Versioned releases

Pushing a tag that starts with `v`, for example `v0.8.0`, triggers the same clean Windows build. After the build succeeds, the workflow creates (or updates) a GitHub Release containing:

- `CloudIPResolver.exe`
- `CloudIPResolver.exe.sha256`
- automatically generated release notes

Release assets are the normal user-facing download location and remain attached to the release until the release is deleted.

The workflow refuses to publish a release if the tag version does not match `cloud_ip_resolver.__version__`. For example, a `v0.8.1` tag will fail if the application still reports version `0.8.0`.

## Create a release

Before tagging, make sure the application version and Windows version metadata have been updated and the full test suite passes. Then, from an up-to-date `main` branch:

```powershell
git pull
git status
git tag -a v0.8.0 -m "Cloud IP Resolver v0.8.0"
git push origin v0.8.0
```

GitHub Actions will then test, build and publish the release automatically.

## Download locations

For a normal `main` build, open the repository's **Actions** tab, open the completed **Windows build and release** run, then download the artifact shown at the bottom of the run page.

For a versioned build, open the repository's **Releases** page and download `CloudIPResolver.exe` from the release assets.

## Private repository note

When the repository is private, both Actions artifacts and GitHub Release assets are only available to users who have permission to access the repository. If the repository is made public later, its public release assets can be downloaded without repository collaborator access.

## Checksum verification

A release also includes `CloudIPResolver.exe.sha256`. On Windows, users can verify the downloaded executable with:

```powershell
Get-FileHash .\CloudIPResolver.exe -Algorithm SHA256
```

The returned hash should match the hexadecimal value in `CloudIPResolver.exe.sha256`.
