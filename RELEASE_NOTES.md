# Cloud IP Resolver v0.8.0

The first packaged Windows release of Cloud IP Resolver. It provides a standalone desktop interface for checking IP addresses against the current published AWS, Microsoft Azure and Google Cloud network ranges.

## Download

Under **Assets** on this release, download:

- `CloudIPResolver.exe` — the standalone Windows application.
- `CloudIPResolver.exe.sha256` — optional SHA-256 checksum for verifying the download.

There is no installer and no Python installation is required. Save `CloudIPResolver.exe` somewhere convenient and double-click it to run.

## How to use

1. Prepare a CSV containing an `IPAddress` column.
2. Open `CloudIPResolver.exe`.
3. Select the input CSV.
4. Choose AWS, Azure and/or Google Cloud.
5. Confirm the output CSV location.
6. Click **Resolve**.
7. Review the match summary and use **Open Output Folder** to access the generated CSV.

Example input:

```csv
IPAddress
20.169.11.34
8.8.8.8
2600:1900::1
```

For more detail, see the [Cloud IP Resolver user guide](https://github.com/danrichardsuk/cloud-ip-resolver/blob/main/USER_GUIDE.md).

## What v0.8.0 includes

- AWS, Microsoft Azure and Google Cloud public range lookup.
- IPv4 and IPv6 support.
- One input file checked against any selected combination of providers.
- Preservation of overlapping CIDR matches, with more-specific prefixes first.
- Combined namespaced CSV output for provider-specific metadata.
- Validation that skips and reports invalid input rows without stopping the run.
- Per-provider prefix counts, matched IP-row counts and CIDR-match counts.
- Clear explanation that one IP can match multiple CIDRs/providers.
- Responsive Windows desktop GUI with progress/status feedback.
- **Open Output Folder** shortcut after a successful run.
- Standalone one-file Windows executable built with PyInstaller.
- Automated clean Windows builds through GitHub Actions.
- SHA-256 checksum included with the release.

## Output terminology

- **Matched IP rows** means input rows that matched at least one published cloud CIDR.
- **CIDR matches** means individual IP-to-prefix matches written to the output CSV.

A single IP can legitimately match multiple published ranges, so the CIDR-match count can be higher than the matched-IP-row count.

## Notes

- A normal run needs internet access because the app downloads the current public provider feeds.
- The executable is currently **unsigned**. Windows SmartScreen may therefore show an unrecognized-app warning. If you obtained the file from this release and trust the source, verify the checksum if desired and use **More info → Run anyway** if Windows requires it.
- The repository is currently private, so only users with repository access can download this release.

## Checksum verification

In PowerShell, run:

```powershell
Get-FileHash .\CloudIPResolver.exe -Algorithm SHA256
```

The returned hash should match the value in `CloudIPResolver.exe.sha256`.
