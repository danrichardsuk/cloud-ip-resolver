# Cloud IP Resolver user guide

Cloud IP Resolver is a standalone Windows desktop utility that checks IP addresses against the published AWS, Microsoft Azure and Google Cloud network ranges and writes the matching cloud metadata to a CSV file.

No Python installation is required for end users.

## Download

1. Open the repository's **Releases** page.
2. Open the latest release.
3. Under **Assets**, download `CloudIPResolver.exe`.
4. Optionally download `CloudIPResolver.exe.sha256` if you want to verify the file checksum.

Because the repository is private, you must have access to the repository to download the release.

## First launch

`CloudIPResolver.exe` is a portable application: there is no installer. Save it somewhere convenient and double-click it to run.

The executable is currently unsigned. Windows SmartScreen may therefore show an **unrecognized app** warning. If you received the file from this repository and have verified that it is the expected release, choose **More info** and then **Run anyway** if required.

## Input CSV

The input file must be a CSV containing a column named:

```text
IPAddress
```

Example:

```csv
IPAddress
20.169.11.34
8.8.8.8
2600:1900::1
```

Valid IPv4 and IPv6 addresses are supported. Invalid values are skipped and reported in the Results window rather than stopping the whole run.

## Run a lookup

1. Click **Browse...** beside **Input CSV** and select the file to check.
2. Select one or more providers: **AWS**, **Azure** and/or **Google Cloud**.
3. Check the **Output CSV** path. By default, the app suggests `output_all.csv` beside the selected input file.
4. Click **Resolve**.
5. Wait for the status to change to **Completed successfully**.
6. Review the summary in the **Results** box.
7. Click **Open Output Folder** to open the folder containing the generated CSV.

The app downloads the current public range feeds for the selected providers, so an internet connection is required during a normal run.

## Understanding the results

The Results window uses two important counts:

- **Matched IP rows** — input rows that matched at least one published cloud CIDR.
- **CIDR matches** — individual IP-to-prefix matches written to the output CSV.

One IP row can match more than one published CIDR, and can also match ranges from more than one provider. It is therefore normal for the number of CIDR matches to be higher than the number of matched IP rows.

For example, an Azure IP can legitimately fall inside both a narrow service-specific prefix and a broader Azure prefix. Both matches are retained, with the most-specific prefix listed first.

## Output CSV

The combined GUI output uses this schema:

```text
IPAddress,Provider,Prefix,Service,Region,AWS_NetworkBorderGroup,Azure_ServiceTagName,Azure_NetworkFeatures,GCP_Scope
```

Provider-specific fields are only populated for the relevant provider. Unmatched input addresses are omitted from the output, while duplicate input rows and overlapping CIDR matches are preserved.

## Verify the download checksum

Each release includes `CloudIPResolver.exe.sha256`.

From PowerShell in the folder containing the downloaded EXE, run:

```powershell
Get-FileHash .\CloudIPResolver.exe -Algorithm SHA256
```

Compare the returned hash with the hexadecimal value in `CloudIPResolver.exe.sha256`.

## Troubleshooting

If the app reports that provider feeds cannot be loaded, check that the computer has internet access and that a corporate proxy, firewall or endpoint-security product is not blocking the connection.

If some input values are listed as invalid/skipped, correct those rows in the source CSV and run the file again. A valid row should contain a normal IPv4 or IPv6 address rather than a hostname, CIDR, blank value or placeholder such as `0`.
