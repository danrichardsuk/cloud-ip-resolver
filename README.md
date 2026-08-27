# Cloud IP Resolver

Cloud IP Resolver matches public IP addresses against published cloud-provider IP ranges and returns the public metadata associated with each match.

The project is being rebuilt from an existing PowerShell proof of concept into a reusable Python engine that can later power both a command-line tool and a self-contained Windows desktop application.

## Goals

- Support AWS, Microsoft Azure, and Google Cloud published IP ranges.
- Support IPv4 and IPv6 correctly, including non-byte-aligned CIDR prefixes.
- Preserve all matching provider prefixes rather than assuming the first match is the only match.
- Allow separate input lists for AWS, Azure, and Google Cloud.
- Allow a single input list to be checked against multiple providers.
- Produce separate provider outputs or a combined result set.
- Package the desktop application as a standalone Windows executable so end users do not need Python installed.

## Architecture

```text
Input files / Desktop GUI / CLI
              |
              v
        Workflow layer
              |
              v
        Resolver engine
              |
              v
         Prefix matcher
              |
      +-------+-------+
      |       |       |
     AWS    Azure    GCP
```

Provider adapters are responsible only for downloading and translating provider-specific data into a common `CloudPrefix` model. Matching is performed once by the shared resolver engine. `MultiProviderWorkflow` loads any configured set of provider adapters and resolves one shared input list, so the same workflow can be reused by the CLI and future desktop GUI.

## Current status

All three provider adapters have been implemented and validated against the original PowerShell scripts on the real input datasets. The unified multi-provider workflow is also implemented.

The project currently includes:

- common prefix and result models
- shared IPv4/IPv6 matcher
- AWS `ip-ranges.json` download and parsing
- Azure Public Service Tags discovery, download and parsing
- Google Cloud `cloud.json` download and parsing
- reusable multi-provider workflow layer
- provider metadata preservation
- CSV input validation
- PowerShell-compatible AWS, Azure, and Google Cloud output CSVs
- parity comparison commands for all three legacy PowerShell outputs
- one-input/all-provider combined output
- unit and integration-style tests for matching, provider parsing, CSV handling, comparison behaviour, and unified workflows

The desktop GUI and Windows packaging are the next major milestones.

## Development

Requires Python 3.11 or newer for development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

End users will not be expected to install Python once the Windows executable is introduced.

## Validated performance

All benchmarks used the real legacy input datasets and produced exact row parity with the non-`s` PowerShell implementations.

| Provider | Legacy PowerShell | Python | Speed-up | Output rows |
| --- | ---: | ---: | ---: | ---: |
| AWS | 577.55 s | 1.85 s | ~312x | 1,505 |
| Azure | 916.29 s | 16.43 s | ~55.8x | 4,937 |
| Google Cloud | 682.50 s | 0.36 s | ~1,896x | 42 |

## AWS

### Run the resolver

The input CSV must contain an `IPAddress` column, matching the existing PowerShell input format.

```powershell
cloud-ip-resolver aws input.csv -o output_python.csv
```

The AWS output uses the same five columns as the PowerShell v3 output:

```text
IPAddress,Prefix,Region,Service,NetworkBorderGroup
```

For a fair comparison with the legacy script, use the exact `ip-ranges.json` it downloaded:

```powershell
cloud-ip-resolver aws input.csv -o output_python.csv --ranges-file .\ip-ranges.json
cloud-ip-resolver compare-aws .\output_v3.csv .\output_python.csv
```

The Python implementation also correctly reads AWS `ipv6_prefixes`; the legacy PowerShell v3 script only iterates the IPv4 `prefixes` array.

## Azure

### Run the resolver

```powershell
cloud-ip-resolver azure input.csv -o output_python.csv
```

When no range file is supplied, the resolver discovers the current JSON link from Microsoft's Azure IP Ranges and Service Tags – Public Cloud download page and downloads it automatically.

The Azure output preserves the six columns used by the legacy PowerShell v3 script:

```text
IPAddress,Name,Prefix,Region,SystemService,NetworkFeatures
```

For parity testing, run the legacy non-`s` script first and then use the exact `ServiceTags_Public.json` it downloaded:

```powershell
cloud-ip-resolver azure input.csv -o output_python.csv --ranges-file .\ServiceTags_Public.json
cloud-ip-resolver compare-azure .\output_v3.csv .\output_python.csv
```

## Google Cloud

### Run the resolver

```powershell
cloud-ip-resolver gcp input.csv -o output_python.csv
```

When no range file is supplied, the resolver downloads Google's current public Cloud IP range feed directly from `https://www.gstatic.com/ipranges/cloud.json`.

The Google Cloud output preserves the four columns used by the legacy PowerShell v3 script:

```text
IPAddress,Prefix,Service,Scope
```

For parity testing, run `pullGoogleIPInfov3.ps1` first and then use the exact `cloud.json` it downloaded:

```powershell
cloud-ip-resolver gcp input.csv -o output_python.csv --ranges-file .\cloud.json
cloud-ip-resolver compare-gcp .\output_google_cloud.csv .\output_python.csv
```

The Python matcher also handles Google's non-byte-aligned IPv6 prefixes correctly; the legacy PowerShell implementation compares whole bytes and can be inaccurate for prefixes such as `/44`.

## Unified multi-provider workflow

One input CSV can now be checked against AWS, Azure, and Google Cloud in a single run:

```powershell
cloud-ip-resolver all input.csv -o output_all.csv
```

By default, the current feeds for all three providers are downloaded. Saved snapshots can be supplied independently, which is useful for repeatable testing:

```powershell
cloud-ip-resolver all input.csv -o output_all.csv `
  --aws-ranges-file .\ip-ranges.json `
  --azure-ranges-file .\ServiceTags_Public.json `
  --gcp-ranges-file .\cloud.json
```

The combined output schema is:

```text
IPAddress,Provider,Prefix,Service,Region,Scope,NetworkBorderGroup,NetworkFeatures
```

Provider-specific fields are left blank when they do not apply. Azure Service Tag names and Google Cloud scopes are represented in `Scope`.

Combined output preserves the original input order and duplicate input rows. If an IP matches multiple published prefixes, the most-specific CIDR is written first, consistent with the shared resolver. Unmatched input addresses are omitted, matching the existing provider-specific output behaviour.

The separate `aws`, `azure`, and `gcp` commands remain unchanged and continue to produce their legacy-compatible provider-specific CSV formats.

## Invalid input

Invalid or non-canonical IP values are reported and skipped instead of terminating the whole batch. Valid rows retain their original input order and duplicates.
