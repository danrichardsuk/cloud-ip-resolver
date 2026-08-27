"""Tests for Google Cloud feed parsing, matching and legacy CSV output.

The synthetic feed contains overlapping IPv4 ranges plus a non-byte-aligned
IPv6 range so both normal metadata handling and exact IPv6 CIDR membership are
protected by deterministic tests.
"""

import csv
import json
from pathlib import Path

import pytest

from cloud_ip_resolver.io import GCP_OUTPUT_FIELDS, write_gcp_matches_csv
from cloud_ip_resolver.providers.gcp import GcpProvider, parse_gcp_feed
from cloud_ip_resolver.resolver import Resolver

FIXTURE = Path(__file__).parent / "fixtures" / "gcp_cloud.json"


def test_parse_gcp_feed_preserves_metadata() -> None:
    """Verify Google publication metadata, service, scope and original CIDR survive parsing."""

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    feed = parse_gcp_feed(payload)
    assert feed.sync_token == "1234567890"
    assert feed.creation_time == "2026-08-26T01:06:36.277297"
    assert feed.ipv4_count == 2
    assert feed.ipv6_count == 1
    prefix = next(item for item in feed.prefixes if item.scope == "asia-east1")
    assert prefix.service == "Google Cloud"
    assert prefix.metadata["published_prefix"] == "34.80.0.0/15"


def test_gcp_overlapping_ipv4_returns_all_matches() -> None:
    """Return both nested GCP ranges and order the /16 before the broader /15."""

    feed = GcpProvider(ranges_file=FIXTURE).load_feed()
    matches = Resolver(feed.prefixes).resolve_one("34.80.10.20").matches
    assert [match.scope for match in matches] == ["asia-east1-special", "asia-east1"]


def test_gcp_non_byte_aligned_ipv6_is_correct() -> None:
    """Protect bit-accurate matching for an IPv6 /35 boundary."""

    feed = GcpProvider(ranges_file=FIXTURE).load_feed()
    resolver = Resolver(feed.prefixes)
    assert resolver.resolve_one("2600:1900:1000::1").matched
    assert not resolver.resolve_one("2600:1900:2000::1").matched


def test_gcp_writer_uses_legacy_columns(tmp_path: Path) -> None:
    """Ensure GCP-only output keeps the original four-column PowerShell contract."""

    feed = GcpProvider(ranges_file=FIXTURE).load_feed()
    resolutions = Resolver(feed.prefixes).resolve_many(["34.80.10.20"])
    output = tmp_path / "output.csv"
    rows_written = write_gcp_matches_csv(output, resolutions)
    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert rows_written == 2
    assert tuple(rows[0].keys()) == GCP_OUTPUT_FIELDS
    assert {row["Scope"] for row in rows} == {"asia-east1", "asia-east1-special"}
    assert {row["Service"] for row in rows} == {"Google Cloud"}


def test_invalid_prefix_collection_rejected() -> None:
    """Reject a GCP prefixes value that is not the documented list structure."""

    with pytest.raises(ValueError, match="prefixes collection"):
        parse_gcp_feed({"prefixes": {}})


def test_record_requires_exactly_one_address_family() -> None:
    """Reject GCP records with neither or both IPv4/IPv6 prefix fields."""

    with pytest.raises(ValueError, match="exactly one"):
        parse_gcp_feed({"prefixes": [{"service": "Google Cloud", "scope": "global"}]})
    with pytest.raises(ValueError, match="exactly one"):
        parse_gcp_feed({"prefixes": [{"ipv4Prefix": "1.1.1.0/24", "ipv6Prefix": "2001:db8::/32"}]})
