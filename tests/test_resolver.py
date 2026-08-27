"""Tests for resolver batch semantics independent of any real provider."""

from cloud_ip_resolver import CloudPrefix, Resolver


def test_resolver_preserves_input_order_and_duplicates() -> None:
    """Return one result per input row without sorting or de-duplicating values.

    This matters to analysts because two identical source rows should remain two
    rows in downstream reporting, and unmatched rows must retain their original
    position in the in-memory result sequence.
    """

    resolver = Resolver(
        [CloudPrefix.from_cidr(provider="Example", cidr="192.0.2.0/24")]
    )

    results = resolver.resolve_many(["192.0.2.1", "198.51.100.1", "192.0.2.1"])

    assert [str(result.ip) for result in results] == [
        "192.0.2.1",
        "198.51.100.1",
        "192.0.2.1",
    ]
    assert [result.matched for result in results] == [True, False, True]
