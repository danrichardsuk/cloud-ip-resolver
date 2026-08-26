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
        Resolver engine
              |
              v
         Prefix matcher
              |
      +-------+-------+
      |       |       |
     AWS    Azure    GCP
```

Provider adapters are responsible only for downloading and translating provider-specific data into a common `CloudPrefix` model. Matching is performed once by the shared resolver engine.

## Current status

AWS and Azure provider slices are implemented. The project currently includes:

- common prefix and result models
- shared IPv4/IPv6 matcher
- AWS `ip-ranges.json` download and parsing
- Azure Public Service Tags discovery, download and parsing
- provider metadata preservation
- CSV input validation
- PowerShell-compatible AWS and Azure output CSVs
- parity comparison commands for the legacy PowerShell outputs
- unit tests for matching, provider parsing, CSV handling and comparison behaviour

Google Cloud, unified multi-provider workflows, the desktop GUI, and Windows packaging will be added incrementally.

## Development

Requires Python 3.11 or newer for development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

End users will not be expected to install Python once the Windows executable is introduced.

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

The comparison ignores row order while preserving duplicate-row multiplicity.

### Validated AWS benchmark

A real-data parity run on 35,177 valid input IP rows produced exactly 1,505 match rows in both implementations:

```text
Legacy PowerShell: 577.55 seconds
Python resolver:      1.85 seconds
Speed-up:           ~312x
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

### Use a saved Azure Service Tags snapshot

For parity testing, first run the legacy non-`s` PowerShell v3 script, then point the Python resolver at the same `ServiceTags_Public.json` it downloaded:

```powershell
cloud-ip-resolver azure input.csv -o output_python.csv --ranges-file .\ServiceTags_Public.json
cloud-ip-resolver compare-azure .\output_v3.csv .\output_python.csv
```

The non-`s` PowerShell script is the correct parity target because it retains every overlapping service-tag match.

The Azure parser is IPv6-capable even though Microsoft's Public Service Tags download is currently documented as IPv4-only. This avoids repeating the legacy script's whole-byte IPv6 prefix comparison issue if IPv6 prefixes are added later.

## Invalid input

Invalid or non-canonical IP values are reported and skipped instead of terminating the whole batch. Valid rows retain their original input order and duplicates.
