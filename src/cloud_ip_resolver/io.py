"""CSV input and output helpers shared by the CLI and future desktop GUI.

This module has two responsibilities:
1. validate/normalise input IP rows without stopping the whole batch on one bad
   value; and
2. translate provider-independent ``Resolution`` objects back into the exact
   CSV shapes users expect.

The three provider-specific schemas intentionally remain compatible with the
legacy PowerShell outputs.  The combined schema is newer and uses provider-
namespaced columns wherever a concept exists for only one provider.
"""

from __future__ import annotations

from collections.abc import Iterable
import csv
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path

from .models import Resolution

# Legacy-compatible provider schemas. Do not casually rename these: parity
# commands compare them directly with the historical PowerShell files.
AWS_OUTPUT_FIELDS = (
    "IPAddress",
    "Prefix",
    "Region",
    "Service",
    "NetworkBorderGroup",
)
AZURE_OUTPUT_FIELDS = (
    "IPAddress",
    "Name",
    "Prefix",
    "Region",
    "SystemService",
    "NetworkFeatures",
)
GCP_OUTPUT_FIELDS = (
    "IPAddress",
    "Prefix",
    "Service",
    "Scope",
)

# Common concepts stay short. Provider-only concepts are explicitly namespaced
# so an analyst does not infer that, for example, Azure Service Tag Name and GCP
# Scope are the same business concept.
COMBINED_OUTPUT_FIELDS = (
    "IPAddress",
    "Provider",
    "Prefix",
    "Service",
    "Region",
    "AWS_NetworkBorderGroup",
    "Azure_ServiceTagName",
    "Azure_NetworkFeatures",
    "GCP_Scope",
)


@dataclass(frozen=True, slots=True)
class InvalidInput:
    """Describe one input row that could not be interpreted as an IP address."""

    row_number: int
    value: str
    reason: str


@dataclass(frozen=True, slots=True)
class InputBatch:
    """Hold valid IP strings separately from invalid-row diagnostics."""

    values: tuple[str, ...]
    invalid: tuple[InvalidInput, ...]


def read_ip_csv(path: str | Path, *, column: str = "IPAddress") -> InputBatch:
    """Read and validate one IP-address column from a CSV file.

    Args:
        path: Input CSV path.
        column: Header containing the IP values. Defaults to ``IPAddress`` for
            compatibility with the legacy files.

    Returns:
        ``InputBatch`` containing valid values in original order plus a separate
        list of invalid rows and reasons.

    Raises:
        OSError: If the file cannot be opened.
        ValueError: If the requested column does not exist.

    Invalid rows are reported rather than raising immediately.  That lets a
    large analyst-supplied file complete even when a small number of rows need
    cleaning afterwards.
    """

    values: list[str] = []
    invalid: list[InvalidInput] = []

    # utf-8-sig transparently accepts CSVs with or without a UTF-8 BOM, which is
    # common when files have passed through Excel or Windows tooling.
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or column not in reader.fieldnames:
            available = ", ".join(reader.fieldnames or []) or "<none>"
            raise ValueError(
                f"Input CSV must contain a '{column}' column; found: {available}"
            )

        # CSV row 1 is the header, so data rows begin at human-friendly row 2.
        for row_number, row in enumerate(reader, start=2):
            value = (row.get(column) or "").strip()
            if not value:
                invalid.append(InvalidInput(row_number, value, "empty value"))
                continue

            try:
                ip_address(value)
            except ValueError as exc:
                invalid.append(InvalidInput(row_number, value, str(exc)))
                continue

            values.append(value)

    return InputBatch(values=tuple(values), invalid=tuple(invalid))


def write_aws_matches_csv(
    path: str | Path,
    resolutions: Iterable[Resolution],
) -> int:
    """Write AWS matches in the five-column legacy PowerShell format.

    Returns:
        Number of match rows written (header excluded).
    """

    return _write_matches_csv(
        path,
        AWS_OUTPUT_FIELDS,
        resolutions,
        provider="AWS",
        row_factory=lambda resolution, match: {
            "IPAddress": str(resolution.ip),
            "Prefix": str(match.network),
            "Region": match.region or "",
            "Service": match.service or "",
            "NetworkBorderGroup": match.metadata.get("network_border_group") or "",
        },
    )


def write_azure_matches_csv(
    path: str | Path,
    resolutions: Iterable[Resolution],
) -> int:
    """Write Azure matches in the six-column legacy PowerShell format.

    Returns:
        Number of match rows written (header excluded).
    """

    return _write_matches_csv(
        path,
        AZURE_OUTPUT_FIELDS,
        resolutions,
        provider="Azure",
        row_factory=lambda resolution, match: {
            "IPAddress": str(resolution.ip),
            "Name": match.metadata.get("name") or match.scope or "",
            "Prefix": match.metadata.get("published_prefix") or str(match.network),
            "Region": match.region or "",
            "SystemService": match.service or "",
            "NetworkFeatures": match.metadata.get("network_features") or "",
        },
    )


def write_gcp_matches_csv(
    path: str | Path,
    resolutions: Iterable[Resolution],
) -> int:
    """Write Google Cloud matches in the four-column legacy format.

    Returns:
        Number of match rows written (header excluded).
    """

    return _write_matches_csv(
        path,
        GCP_OUTPUT_FIELDS,
        resolutions,
        provider="GCP",
        row_factory=lambda resolution, match: {
            "IPAddress": str(resolution.ip),
            "Prefix": match.metadata.get("published_prefix") or str(match.network),
            "Service": match.service or "",
            "Scope": match.scope or "",
        },
    )


def write_combined_matches_csv(
    path: str | Path,
    resolutions: Iterable[Resolution],
) -> int:
    """Write matches from all providers using the combined analyst-friendly schema.

    Args:
        path: Destination CSV path.
        resolutions: Ordered resolution records from the multi-provider workflow.

    Returns:
        Number of match rows written (header excluded).

    Notes:
        Unmatched inputs are omitted, matching the provider-specific behaviour.
        Provider-only values are populated only for their own provider; the
        corresponding cells remain blank on other providers' rows.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMBINED_OUTPUT_FIELDS)
        writer.writeheader()
        for resolution in resolutions:
            for match in resolution.matches:
                is_aws = match.provider == "AWS"
                is_azure = match.provider == "Azure"
                is_gcp = match.provider == "GCP"

                writer.writerow(
                    {
                        "IPAddress": str(resolution.ip),
                        "Provider": match.provider,
                        "Prefix": match.metadata.get("published_prefix")
                        or str(match.network),
                        "Service": match.service or "",
                        "Region": match.region or "",
                        "AWS_NetworkBorderGroup": (
                            match.metadata.get("network_border_group") or ""
                            if is_aws
                            else ""
                        ),
                        "Azure_ServiceTagName": (
                            match.metadata.get("name") or match.scope or ""
                            if is_azure
                            else ""
                        ),
                        "Azure_NetworkFeatures": (
                            match.metadata.get("network_features") or ""
                            if is_azure
                            else ""
                        ),
                        "GCP_Scope": match.scope or "" if is_gcp else "",
                    }
                )
                row_count += 1

    return row_count


def _write_matches_csv(
    path,
    fields,
    resolutions,
    *,
    provider,
    row_factory,
) -> int:
    """Shared implementation for the three legacy-compatible CSV writers.

    Args:
        path: Destination CSV path.
        fields: Ordered output field names.
        resolutions: Resolution records that may contain several providers.
        provider: Provider name whose matches should be written.
        row_factory: Callable translating one match into a CSV dictionary.

    Returns:
        Number of data rows written.

    Keeping the file-opening/iteration code here prevents small behavioural
    differences from developing between the AWS, Azure and GCP writers.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for resolution in resolutions:
            for match in resolution.matches:
                if match.provider != provider:
                    continue
                writer.writerow(row_factory(resolution, match))
                row_count += 1

    return row_count
