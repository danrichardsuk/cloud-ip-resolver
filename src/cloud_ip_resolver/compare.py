"""Comparison helpers for validating the Python output against legacy output."""

from __future__ import annotations

from collections import Counter
import csv
from pathlib import Path

from .io import AWS_OUTPUT_FIELDS

AwsRow = tuple[str, str, str, str, str]


def compare_aws_csv(
    old_path: str | Path,
    new_path: str | Path,
) -> tuple[Counter[AwsRow], Counter[AwsRow]]:
    """Return rows only in old and only in new, ignoring output ordering."""

    old_rows = _read_aws_rows(old_path)
    new_rows = _read_aws_rows(new_path)
    return old_rows - new_rows, new_rows - old_rows


def _read_aws_rows(path: str | Path) -> Counter[AwsRow]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        missing = [
            field
            for field in AWS_OUTPUT_FIELDS
            if field not in (reader.fieldnames or [])
        ]
        if missing:
            raise ValueError(f"{path} is missing columns: {', '.join(missing)}")

        rows: Counter[AwsRow] = Counter()
        for row in reader:
            values = tuple((row.get(field) or "").strip() for field in AWS_OUTPUT_FIELDS)
            rows[values] += 1
        return rows
