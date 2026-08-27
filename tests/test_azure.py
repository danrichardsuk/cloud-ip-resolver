"""Tests for Azure Service Tags parsing and exact CIDR matching.

The fixture includes overlapping IPv4 tags and a deliberately non-byte-aligned
IPv6 prefix.  The latter protects the Python implementation from reintroducing
the manual whole-byte comparison problem found in the original PowerShell code.
"""

import json
from pathlib import Path

import pytest

from cloud_ip_resolver.providers.azure import AzureProvider, parse_azure_feed
from cloud_ip_resolver.resolver import Resolver

FIXTURE = Path(__file__).parent / "fixtures" / "azure_service_tags.json"


def test_parse_azure_feed_preserves_metadata() -> None:
    """Check publication, service-tag and provider-specific metadata survive parsing."""

    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    feed = parse_azure_feed(payload)

    assert feed.change_number == 999
    assert feed.cloud == "Public"
    assert feed.ipv4_count == 2
    assert feed.ipv6_count == 1

    storage = next(prefix for prefix in feed.prefixes if prefix.scope == "Storage.TestRegion")
    assert storage.service == "Storage"
    assert storage.region == "testregion"
    assert storage.metadata["network_features"] == ""
    assert storage.metadata["published_prefix"] == "20.1.0.0/16"


def test_azure_overlapping_ipv4_returns_all_matches() -> None:
    """Return both a specific Storage tag and its broader AzureCloud tag."""

    feed = AzureProvider(ranges_file=FIXTURE).load_feed()
    matches = Resolver(feed.prefixes).resolve_one("20.1.2.3").matches

    assert [match.scope for match in matches] == [
        "Storage.TestRegion",
        "AzureCloud.TestRegion",
    ]


def test_azure_non_byte_aligned_ipv6_is_correct() -> None:
    """Prove exact bit-level IPv6 membership for a /35 network boundary."""

    feed = AzureProvider(ranges_file=FIXTURE).load_feed()
    resolver = Resolver(feed.prefixes)

    # The first address is inside the /35; the second crosses its true bit boundary.
    assert resolver.resolve_one("2001:db8:3fff::1").matched
    assert not resolver.resolve_one("2001:db8:4000::1").matched


def test_invalid_values_collection_rejected() -> None:
    """Fail clearly when Azure's top-level values collection is not a list."""

    with pytest.raises(ValueError, match="values collection"):
        parse_azure_feed({"values": {}})


def test_invalid_network_features_rejected() -> None:
    """Require Azure networkFeatures to be a list (or null), not arbitrary text."""

    payload = {
        "values": [
            {
                "name": "Example",
                "properties": {
                    "addressPrefixes": ["20.0.0.0/8"],
                    "networkFeatures": "API",
                },
            }
        ]
    }

    with pytest.raises(ValueError, match="networkFeatures"):
        parse_azure_feed(payload)
