"""Compare Python CSV output with the original PowerShell output.

Parity checks need to answer "are these the same rows?" without being distracted
by harmless row-order differences.  ``Counter`` is used as a multiset: it keeps
both the row values and how many times each row occurred, so duplicate inputs
are still validated correctly.
"""

from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path

from .io import AWS_OUTPUT_FIELDS, AZURE_OUTPUT_FIELDS, GCP_OUTPUT_FIELDS

# Named tuple aliases make the return types readable without creating extra
# runtime classes. Their lengths mirror the provider-specific CSV schemas.
AwsRow = tuple[str, str, str, str, str]
AzureRow = tuple[str, str, str, str, str, str]
GcpRow = tuple[str, str, str, str]


def compare_aws_csv(
    old_path: str | Path,
    new_path: str | Path,
) -> tuple[Counter[AwsRow], Counter[AwsRow]]:
    """Compare legacy and Python AWS CSVs while ignoring row order.

    Args:
        old_path: CSV produced by the legacy PowerShell implementation.
        new_path: CSV produced by the Python implementation.

    Returns:
        Two counters: rows only in the legacy file, then rows only in Python.
        Both are empty when parity is exact.
    """

    old_rows = _read_rows(old_path, AWS_OUTPUT_FIELDS)
    new_rows = _read_rows(new_path, AWS_OUTPUT_FIELDS)
    return old_rows - new_rows, new_rows - old_rows


def compare_azure_csv(
    old_path: str | Path,
    new_path: str | Path,
) -> tuple[Counter[AzureRow], Counter[AzureRow]]:
    """Compare legacy and Python Azure CSVs as duplicate-aware multisets."""

    old_rows = _read_rows(old_path, AZURE_OUTPUT_FIELDS)
    new_rows = _read_rows(new_path, AZURE_OUTPUT_FIELDS)
    return old_rows - new_rows, new_rows - old_rows


def compare_gcp_csv(
    old_path: str | Path,
    new_path: str | Path,
) -> tuple[Counter[GcpRow], Counter[GcpRow]]:
    """Compare legacy and Python GCP CSVs as duplicate-aware multisets."""

    old_rows = _read_rows(old_path, GCP_OUTPUT_FIELDS)
    new_rows = _read_rows(new_path, GCP_OUTPUT_FIELDS)
    return old_rows - new_rows, new_rows - old_rows


def _read_rows(
    path: str | Path,
    fields: tuple[str, ...],
) -> Counter[tuple[str, ...]]:
    """Read selected CSV columns into a duplicate-aware ``Counter``.

    Args:
        path: CSV to inspect.
        fields: Expected fields and their comparison order.

    Returns:
        Counter keyed by complete row tuples. A value greater than one means the
        exact same row appeared multiple times.

    Raises:
        ValueError: If any required column is absent. Failing early here makes a
        schema mismatch clearer than reporting every row as different.
    """

    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [
            field for field in fields if field not in (reader.fieldnames or [])
        ]
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

        rows: Counter[tuple[str, ...]] = Counter()
        for row in reader:
            # Whitespace is not meaningful in these generated fields, so trim it
            # before comparison to avoid false differences from CSV formatting.
            values = tuple((row.get(field) or "").strip() for field in fields)
            rows[values] += 1
        return rows
