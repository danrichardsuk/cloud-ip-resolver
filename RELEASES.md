# GitHub Actions and releases

Cloud IP Resolver uses GitHub Actions to build the Windows executable on a clean Windows runner and make it available in two different ways.

User-facing release information is kept separately:

- `RELEASE_NOTES.md` — curated notes for the current application version.
- `USER_GUIDE.md` — download, launch, input/output and troubleshooting instructions for end users.

## Development builds

Every push to `main` runs the test suite and builds `CloudIPResolver.exe`. The workflow uploads the EXE and a SHA-256 checksum as a GitHub Actions artifact.

Actions artifacts are intended for development/testing. They are retained for 30 days by this workflow and are downloaded from the relevant workflow run.

## Versioned releases

Pushing a tag that starts with `v`, for example `v0.8.0`, triggers the same clean Windows build. After the build succeeds, the workflow creates (or updates) a GitHub Release containing:

- `CloudIPResolver.exe`
- `CloudIPResolver.exe.sha256`
- the curated user-facing contents of `RELEASE_NOTES.md`

Release assets are the normal user-facing download location and remain attached to the release until the release is deleted.

The workflow refuses to publish a release if the tag version does not match `cloud_ip_resolver.__version__`. For example, a `v0.8.1` tag will fail if the application still reports version `0.8.0`.

When `RELEASE_NOTES.md` is updated on `main`, a small companion workflow updates the GitHub Release whose tag matches the current application version. If that release has not been created yet, the sync workflow simply leaves the notes ready for the eventual tagged release.

## Create a release

Before tagging:

1. update the application version and Windows version metadata
2. update `RELEASE_NOTES.md` for the new version
3. make sure the full test suite passes
4. start from an up-to-date `main` branch

Then create and push the version tag:

```powershell
git pull
git status
git tag -a v0.8.0 -m "Cloud IP Resolver v0.8.0"
git push origin v0.8.0
```

GitHub Actions will then test, build and publish the release automatically.

## Download locations

For a normal `main` build, open the repository's **Actions** tab, open the completed **Windows build and release** run, then download the artifact shown at the bottom of the run page.

For a versioned build, open the repository's **Releases** page and download `CloudIPResolver.exe` from the release assets. End users should normally use the versioned Release rather than an Actions artifact.

See `USER_GUIDE.md` for the normal end-user workflow.

## Private repository note

When the repository is private, both Actions artifacts and GitHub Release assets are only available to users who have permission to access the repository. If the repository is made public later, its public release assets can be downloaded without repository collaborator access.

## Checksum verification

A release also includes `CloudIPResolver.exe.sha256`. On Windows, users can verify the downloaded executable with:

```powershell
Get-FileHash .\CloudIPResolver.exe -Algorithm SHA256
```

The returned hash should match the hexadecimal value in `CloudIPResolver.exe.sha256`.
