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
    """Read canonical IPv4/IPv6 values from a CSV column.

    Invalid values are collected instead of aborting the entire batch.
    Row numbers use the physical CSV row number, including the header row.
    """

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
            raw = row.get(column)
            value = (raw or "").strip()
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
    """Write AWS matches using the same five columns as the PowerShell v3 output."""

    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0

    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AWS_OUTPUT_FIELDS)
        writer.writeheader()

        for resolution in resolutions:
            for match in resolution.matches:
                if match.provider != "AWS":
                    continue
                writer.writerow(
                    {
                        "IPAddress": str(resolution.ip),
                        "Prefix": str(match.network),
                        "Region": match.region or "",
                        "Service": match.service or "",
                        "NetworkBorderGroup": match.metadata.get(
                            "network_border_group"
                        )
                        or "",
                    }
                )
                row_count += 1

    return row_count
