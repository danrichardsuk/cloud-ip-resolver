"""Common data models used by every cloud provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from ipaddress import (
    IPv4Address,
    IPv4Network,
    IPv6Address,
    IPv6Network,
    ip_network,
)
from typing import Any, Mapping

IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network


@dataclass(frozen=True, slots=True)
class CloudPrefix:
    """A provider IP range normalised into a provider-independent model."""

    provider: str
    network: IPNetwork
    service: str | None = None
    region: str | None = None
    scope: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_cidr(
        cls,
        *,
        provider: str,
        cidr: str,
        service: str | None = None,
        region: str | None = None,
        scope: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "CloudPrefix":
        """Create a normalised prefix from a CIDR string."""

        return cls(
            provider=provider,
            network=ip_network(cidr, strict=False),
            service=service,
            region=region,
            scope=scope,
            metadata=metadata or {},
        )


@dataclass(frozen=True, slots=True)
class Resolution:
    """All published cloud-prefix matches for one IP address."""

    ip: IPAddress
    matches: tuple[CloudPrefix, ...]

    @property
    def matched(self) -> bool:
        return bool(self.matches)

    @property
    def providers(self) -> tuple[str, ...]:
        """Return unique provider names while preserving match order."""

        return tuple(dict.fromkeys(match.provider for match in self.matches))
