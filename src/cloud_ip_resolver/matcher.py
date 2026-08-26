"""Shared IPv4/IPv6 prefix matching."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address

from .models import CloudPrefix, IPAddress


class PrefixMatcher:
    """Efficiently match IP addresses against normalised cloud prefixes.

    Prefixes are bucketed by the first IPv4 octet or IPv6 hextet before
    membership tests are performed. Very broad ranges that span more than
    one bucket are kept in a small shared list so correctness is preserved.
    """

    def __init__(self, prefixes: Iterable[CloudPrefix]) -> None:
        self._ipv4_buckets: dict[int, list[CloudPrefix]] = defaultdict(list)
        self._ipv6_buckets: dict[int, list[CloudPrefix]] = defaultdict(list)
        self._ipv4_broad: list[CloudPrefix] = []
        self._ipv6_broad: list[CloudPrefix] = []

        for prefix in prefixes:
            network = prefix.network
            if network.version == 4:
                if network.prefixlen >= 8:
                    bucket = int(network.network_address) >> 24
                    self._ipv4_buckets[bucket].append(prefix)
                else:
                    self._ipv4_broad.append(prefix)
            else:
                if network.prefixlen >= 16:
                    bucket = int(network.network_address) >> 112
                    self._ipv6_buckets[bucket].append(prefix)
                else:
                    self._ipv6_broad.append(prefix)

    def find_all(self, value: str | IPAddress) -> tuple[CloudPrefix, ...]:
        """Return every prefix containing the supplied IP address.

        Matches are ordered from most-specific to least-specific prefix.
        """

        address = ip_address(value) if isinstance(value, str) else value
        candidates = self._candidates(address)
        matches = [prefix for prefix in candidates if address in prefix.network]

        return tuple(
            sorted(
                matches,
                key=lambda prefix: (
                    -prefix.network.prefixlen,
                    prefix.provider,
                    prefix.service or "",
                    prefix.region or "",
                ),
            )
        )

    def _candidates(self, address: IPAddress) -> list[CloudPrefix]:
        if isinstance(address, IPv4Address):
            bucket = int(address) >> 24
            return self._ipv4_broad + self._ipv4_buckets.get(bucket, [])

        if isinstance(address, IPv6Address):
            bucket = int(address) >> 112
            return self._ipv6_broad + self._ipv6_buckets.get(bucket, [])

        raise TypeError(f"Unsupported address type: {type(address)!r}")
