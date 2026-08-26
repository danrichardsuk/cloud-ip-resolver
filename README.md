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

Initial project foundation:

- common prefix and result models
- shared IPv4/IPv6 matcher
- provider adapter interface
- unit tests for matching behaviour

Provider downloads, CSV handling, GUI, and Windows packaging will be added incrementally.

## Development

Requires Python 3.11 or newer for development.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest
```

End users will not be expected to install Python once the Windows executable is introduced.
