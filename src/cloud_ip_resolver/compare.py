"""Comparison helpers for validating Python output against legacy output."""

from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path

from .io import AWS_OUTPUT_FIELDS, AZURE_OUTPUT_FIELDS

AwsRow = tuple[str, str, str, str, str]
AzureRow = tuple[str, str, str, str, str, str]


def compare_aws_csv(
    old_path: str | Path,
    new_path: str | Path,
) -> tuple[Counter[AwsRow], Counter[AwsRow]]:
    old_rows = _read_rows(old_path, AWS_OUTPUT_FIELDS)
    new_rows = _read_rows(new_path, AWS_OUTPUT_FIELDS)
    return old_rows - new_rows, new_rows - old_rows


def compare_azure_csv(
    old_path: str | Path,
    new_path: str | Path,
) -> tuple[Counter[AzureRow], Counter[AzureRow]]:
    old_rows = _read_rows(old_path, AZURE_OUTPUT_FIELDS)
    new_rows = _read_rows(new_path, AZURE_OUTPUT_FIELDS)
    return old_rows - new_rows, new_rows - old_rows


def _read_rows(
    path: str | Path,
    fields: tuple[str, ...],
) -> Counter[tuple[str, ...]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [
            field for field in fields if field not in (reader.fieldnames or [])
        ]
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

        rows: Counter[tuple[str, ...]] = Counter()
        for row in reader:
            values = tuple((row.get(field) or "").strip() for field in fields)
            rows[values] += 1
        return rows
