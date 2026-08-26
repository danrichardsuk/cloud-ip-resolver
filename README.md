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

AWS is the first complete provider slice. The project currently includes:

- common prefix and result models
- shared IPv4/IPv6 matcher
- AWS `ip-ranges.json` download and parsing
- both AWS IPv4 (`prefixes`) and IPv6 (`ipv6_prefixes`) ranges
- AWS region, service, and network border group metadata
- CSV input validation
- PowerShell-compatible AWS match CSV output
- a parity comparison command for legacy PowerShell output
- unit tests for matching, AWS parsing, CSV handling, and comparison behaviour

Azure, Google Cloud, the desktop GUI, and Windows packaging will be added incrementally.

## Development

Requires Python 3.11 or newer for development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

End users will not be expected to install Python once the Windows executable is introduced.

## Run the AWS resolver

The input CSV must contain an `IPAddress` column, matching the existing PowerShell input format.

```powershell
cloud-ip-resolver aws input.csv -o output_python.csv
```

This downloads the current AWS public IP range feed and writes matched rows using the same five columns as the PowerShell v3 output:

```text
IPAddress,Prefix,Region,Service,NetworkBorderGroup
```

Invalid or non-canonical IP values are reported and skipped instead of terminating the whole batch.

### Use a saved AWS range snapshot

For a fair comparison with the existing PowerShell script, run the PowerShell script first and then point the Python resolver at the `ip-ranges.json` it downloaded:

```powershell
cloud-ip-resolver aws input.csv -o output_python.csv --ranges-file .\ip-ranges.json
```

This ensures both implementations use exactly the same AWS publication.

## Compare with the PowerShell output

Run the original non-`s` PowerShell v3 script so that all overlapping AWS matches are retained. Then compare its output with the Python output:

```powershell
cloud-ip-resolver compare-aws .\output_v3.csv .\output_python.csv
```

The comparison ignores row order but preserves duplicate rows. A successful comparison prints:

```text
MATCH: both CSVs contain the same AWS match rows (row order ignored).
```

The Python implementation intentionally adds correct AWS IPv6 support by reading `ipv6_prefixes`. The original PowerShell v3 script only iterates the AWS IPv4 `prefixes` array, so IPv6 inputs are expected to produce additional correct rows in the Python output.
