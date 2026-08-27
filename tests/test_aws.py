"""Tests for AWS feed parsing, metadata preservation and matching behaviour.

These tests use a small saved fixture rather than the live internet feed.  That
keeps the suite deterministic while still representing the important AWS
concepts: overlapping IPv4 ranges, IPv6 ranges and provider-specific metadata.
"""

from pathlib import Path

from cloud_ip_resolver.providers.aws import AwsProvider, parse_aws_feed
from cloud_ip_resolver.resolver import Resolver

FIXTURE = Path(__file__).parent / "fixtures" / "aws_ip_ranges.json"


def test_aws_provider_reads_ipv4_and_ipv6_from_saved_feed() -> None:
    """Verify one saved AWS publication loads metadata and both address families.

    A beginner can read this as a basic adapter contract: given valid AWS JSON,
    ``load_feed`` should expose publication metadata and count every IPv4/IPv6
    prefix instead of silently ignoring one family.
    """

    feed = AwsProvider(ranges_file=FIXTURE).load_feed()

    assert feed.sync_token == "1234567890"
    assert feed.create_date == "2026-08-26-00-00-00"
    assert feed.ipv4_count == 2
    assert feed.ipv6_count == 1


def test_aws_metadata_is_preserved() -> None:
    """Ensure AWS-only fields survive normalisation for later CSV reporting."""

    feed = AwsProvider(ranges_file=FIXTURE).load_feed()
    ec2 = next(prefix for prefix in feed.prefixes if prefix.service == "EC2")

    assert ec2.region == "us-east-1"
    assert ec2.metadata["network_border_group"] == "us-east-1"


def test_aws_overlapping_matches_are_all_returned() -> None:
    """Confirm overlapping AWS ranges are retained, most-specific first.

    The fixture deliberately places the test IP in an EC2 /25 and a broader
    AMAZON /24.  Returning both matches preserves information that the legacy
    first-match-only script variant could discard.
    """

    feed = AwsProvider(ranges_file=FIXTURE).load_feed()
    resolution = Resolver(feed.prefixes).resolve_one("198.51.100.10")

    assert [match.service for match in resolution.matches] == ["EC2", "AMAZON"]


def test_aws_ipv6_ranges_are_resolved() -> None:
    """Verify the AWS IPv6 collection participates in normal resolution."""

    feed = AwsProvider(ranges_file=FIXTURE).load_feed()
    resolution = Resolver(feed.prefixes).resolve_one("2001:db8:1234::abcd")

    assert resolution.matched
    assert resolution.matches[0].network.version == 6


def test_parse_rejects_missing_prefix_key() -> None:
    """Reject malformed AWS records with a useful reference to the missing key."""

    payload = {"prefixes": [{}], "ipv6_prefixes": []}

    try:
        parse_aws_feed(payload)
    except ValueError as exc:
        assert "ip_prefix" in str(exc)
    else:
        raise AssertionError("Expected invalid AWS record to raise ValueError")
