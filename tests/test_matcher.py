from cloud_ip_resolver import CloudPrefix, PrefixMatcher


def test_ipv4_returns_all_overlapping_matches_most_specific_first() -> None:
    matcher = PrefixMatcher(
        [
            CloudPrefix.from_cidr(provider="Example", cidr="10.0.0.0/8", service="broad"),
            CloudPrefix.from_cidr(provider="Example", cidr="10.10.0.0/16", service="specific"),
        ]
    )

    matches = matcher.find_all("10.10.1.25")

    assert [match.service for match in matches] == ["specific", "broad"]


def test_ipv4_very_broad_prefix_still_matches_across_bucket_boundary() -> None:
    matcher = PrefixMatcher(
        [CloudPrefix.from_cidr(provider="Example", cidr="10.0.0.0/7")]
    )

    assert matcher.find_all("11.10.20.30")


def test_ipv6_non_byte_aligned_prefix_matches_correctly() -> None:
    matcher = PrefixMatcher(
        [CloudPrefix.from_cidr(provider="Example", cidr="2600:1900::/35")]
    )

    assert matcher.find_all("2600:1900:1000::1")
    assert not matcher.find_all("2600:1900:2000::1")
