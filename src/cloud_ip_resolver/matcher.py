"""Fast, shared IPv4/IPv6 CIDR matching for every provider.

A naive resolver would compare every input IP with every published prefix.  On
large Azure feeds that becomes expensive.  ``PrefixMatcher`` first groups
prefixes into coarse buckets, then asks Python's ``ipaddress`` library to do the
final exact membership check.  This keeps the optimisation simple while still
handling difficult prefixes such as non-byte-aligned IPv6 CIDRs correctly.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from ipaddress import IPv4Address, IPv6Address, ip_address

from .models import CloudPrefix, IPAddress


class PrefixMatcher:
    """Index cloud prefixes and return all ranges that contain an address.

    IPv4 prefixes of ``/8`` or longer are bucketed by their first octet.
    IPv6 prefixes of ``/16`` or longer are bucketed by their first hextet.
    Broader networks span more than one such bucket, so they are kept in small
    shared lists and included in every candidate search for that address family.
    """

    def __init__(self, prefixes: Iterable[CloudPrefix]) -> None:
        """Build lookup buckets once so repeated IP resolution is inexpensive.

        Args:
            prefixes: Any iterable of normalised ``CloudPrefix`` objects.

        The integer shifts below extract the most-significant 8 bits (IPv4) or
        16 bits (IPv6).  They are an optimisation only; actual correctness still
        comes from ``address in prefix.network`` inside :meth:`find_all`.
        """

        self._ipv4_buckets: dict[int, list[CloudPrefix]] = defaultdict(list)
        self._ipv6_buckets: dict[int, list[CloudPrefix]] = defaultdict(list)
        self._ipv4_broad: list[CloudPrefix] = []
        self._ipv6_broad: list[CloudPrefix] = []

        for prefix in prefixes:
            network = prefix.network
            if network.version == 4:
                if network.prefixlen >= 8:
                    # ``>> 24`` leaves the first octet of a 32-bit IPv4 value.
                    bucket = int(network.network_address) >> 24
                    self._ipv4_buckets[bucket].append(prefix)
                else:
                    self._ipv4_broad.append(prefix)
            else:
                if network.prefixlen >= 16:
                    # ``>> 112`` leaves the first 16 bits of a 128-bit IPv6 value.
                    bucket = int(network.network_address) >> 112
                    self._ipv6_buckets[bucket].append(prefix)
                else:
                    self._ipv6_broad.append(prefix)

    def find_all(self, value: str | IPAddress) -> tuple[CloudPrefix, ...]:
        """Return every published prefix containing one IP address.

        Args:
            value: Textual IP address or an already-parsed ``ipaddress`` object.

        Returns:
            A tuple of matches ordered from most-specific CIDR to least-specific.
            Additional provider/service/region fields provide deterministic
            ordering when prefixes have the same prefix length.
        """

        address = ip_address(value) if isinstance(value, str) else value
        candidates = self._candidates(address)

        # This is the authoritative membership test.  Using ``ipaddress`` avoids
        # the legacy PowerShell scripts' partial-byte IPv6 comparison problem.
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
        """Return the small candidate set for an address before exact matching.

        Args:
            address: Parsed IPv4 or IPv6 address.

        Returns:
            Prefixes in the address's bucket plus any very broad prefixes that
            cannot safely be assigned to a single bucket.

        Raises:
            TypeError: If a caller passes an unsupported address object.
        """

        if isinstance(address, IPv4Address):
            bucket = int(address) >> 24
            return self._ipv4_broad + self._ipv4_buckets.get(bucket, [])

        if isinstance(address, IPv6Address):
            bucket = int(address) >> 112
            return self._ipv6_broad + self._ipv6_buckets.get(bucket, [])

        raise TypeError(f"Unsupported address type: {type(address)!r}")
