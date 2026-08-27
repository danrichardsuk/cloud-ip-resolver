"""CSV input/output helpers used by the CLI and future desktop UI."""

from __future__ import annotations

from collections.abc import Iterable
import csv
from dataclasses import dataclass
from ipaddress import ip_address
from pathlib import Path

from .models import Resolution

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
COMBINED_OUTPUT_FIELDS = (
    "IPAddress",
    "Provider",
    "Prefix",
    "Service",
    "Region",
    "Scope",
    "NetworkBorderGroup",
    "NetworkFeatures",
)


@dataclass(frozen=True, slots=True)
class InvalidInput:
    row_number: int
    value: str
    reason: str


@dataclass(frozen=True, slots=True)
class InputBatch:
    values: tuple[str, ...]
    invalid: tuple[InvalidInput, ...]


def read_ip_csv(path: str | Path, *, column: str = "IPAddress") -> InputBatch:
    """Read canonical IPv4/IPv6 values from a CSV column."""

    values: list[str] = []
    invalid: list[InvalidInput] = []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or column not in reader.fieldnames:
            available = ", ".join(reader.fieldnames or []) or "<none>"
            raise ValueError(
                f"Input CSV must contain a '{column}' column; found: {available}"
            )

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
    """Write AWS matches using the legacy PowerShell v3 columns."""

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
    """Write Azure matches using the legacy PowerShell v3 columns."""

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
    """Write GCP matches using the legacy PowerShell v3 columns."""

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
    """Write every provider match using the unified multi-provider schema.

    Unmatched input addresses are intentionally omitted, matching the existing
    provider-specific output behaviour.
    """

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COMBINED_OUTPUT_FIELDS)
        writer.writeheader()
        for resolution in resolutions:
            for match in resolution.matches:
                writer.writerow(
                    {
                        "IPAddress": str(resolution.ip),
                        "Provider": match.provider,
                        "Prefix": match.metadata.get("published_prefix")
                        or str(match.network),
                        "Service": match.service or "",
                        "Region": match.region or "",
                        "Scope": match.scope or "",
                        "NetworkBorderGroup": match.metadata.get(
                            "network_border_group"
                        )
                        or "",
                        "NetworkFeatures": match.metadata.get("network_features")
                        or "",
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
