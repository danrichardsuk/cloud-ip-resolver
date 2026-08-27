"""Tests for general CSV input validation and AWS output compatibility."""

import csv
from pathlib import Path

from cloud_ip_resolver.io import read_ip_csv, write_aws_matches_csv
from cloud_ip_resolver.providers.aws import AwsProvider
from cloud_ip_resolver.resolver import Resolver

FIXTURE = Path(__file__).parent / "fixtures" / "aws_ip_ranges.json"


def test_read_ip_csv_skips_invalid_values(tmp_path: Path) -> None:
    """Keep valid IPv4/IPv6 rows while recording an invalid shorthand value.

    The input deliberately includes ``0`` because the old .NET parser accepted
    forms that Python's stricter ``ipaddress`` parser rejects.  The batch should
    continue and report that row instead of failing the entire file.
    """

    source = tmp_path / "input.csv"
    source.write_text(
        "IPAddress\n198.51.100.10\n0\n2001:db8:1234::1\n",
        encoding="utf-8",
    )

    batch = read_ip_csv(source)

    assert batch.values == ("198.51.100.10", "2001:db8:1234::1")
    assert len(batch.invalid) == 1
    assert batch.invalid[0].value == "0"


def test_aws_output_matches_legacy_column_shape(tmp_path: Path) -> None:
    """Protect the exact AWS header and all overlapping service rows."""

    feed = AwsProvider(ranges_file=FIXTURE).load_feed()
    resolutions = Resolver(feed.prefixes).resolve_many(["198.51.100.10"])
    output = tmp_path / "output.csv"

    rows_written = write_aws_matches_csv(output, resolutions)

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert rows_written == 2
    assert list(rows[0]) == [
        "IPAddress",
        "Prefix",
        "Region",
        "Service",
        "NetworkBorderGroup",
    ]
    assert {row["Service"] for row in rows} == {"AMAZON", "EC2"}
