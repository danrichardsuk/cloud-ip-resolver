import json
from pathlib import Path

import pytest

from cloud_ip_resolver.providers.azure import AzureProvider, parse_azure_feed
from cloud_ip_resolver.resolver import Resolver

FIXTURE = Path(__file__).parent / "fixtures" / "azure_service_tags.json"


def test_parse_azure_feed_preserves_metadata() -> None:
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
    feed = AzureProvider(ranges_file=FIXTURE).load_feed()
    matches = Resolver(feed.prefixes).resolve_one("20.1.2.3").matches

    assert [match.scope for match in matches] == [
        "Storage.TestRegion",
        "AzureCloud.TestRegion",
    ]


def test_azure_non_byte_aligned_ipv6_is_correct() -> None:
    feed = AzureProvider(ranges_file=FIXTURE).load_feed()
    resolver = Resolver(feed.prefixes)

    assert resolver.resolve_one("2001:db8:3fff::1").matched
    assert not resolver.resolve_one("2001:db8:4000::1").matched


def test_invalid_values_collection_rejected() -> None:
    with pytest.raises(ValueError, match="values collection"):
        parse_azure_feed({"values": {}})


def test_invalid_network_features_rejected() -> None:
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
