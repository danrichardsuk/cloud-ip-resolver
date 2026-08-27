"""Provider-independent data models shared by the whole application.

AWS, Azure and Google publish different JSON shapes.  The adapter modules turn
those provider-specific records into the common classes in this file.  The
matcher and resolver can therefore work with one consistent representation
instead of containing provider-specific branches.
"""

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

# Type aliases make signatures easier to read while still supporting both
# address families everywhere in the resolver.
IPAddress = IPv4Address | IPv6Address
IPNetwork = IPv4Network | IPv6Network


@dataclass(frozen=True, slots=True)
class CloudPrefix:
    """Represent one published cloud CIDR in a provider-independent form.

    Attributes:
        provider: Short provider name such as ``AWS``, ``Azure`` or ``GCP``.
        network: Parsed IPv4 or IPv6 network used for real membership tests.
        service: Provider service label when one exists, for example ``EC2``.
        region: Provider region when the feed supplies one.
        scope: Provider-defined grouping that does not fit the common fields.
        metadata: Extra provider-specific values preserved for output/reporting.

    The dataclass is frozen so a parsed prefix cannot accidentally be changed
    after it has been indexed by the matcher.
    """

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
        """Build a :class:`CloudPrefix` from a provider's CIDR string.

        Args:
            provider: Name assigned to the source provider.
            cidr: Network in CIDR notation, for example ``10.0.0.0/8``.
            service: Optional service supplied by the provider feed.
            region: Optional provider region.
            scope: Optional provider-specific grouping or tag name.
            metadata: Any extra values that should survive normalisation.

        Returns:
            A normalised, immutable ``CloudPrefix`` instance.

        Notes:
            ``strict=False`` allows a feed to contain host bits in the textual
            CIDR and normalises it to the actual network boundary.  Python's
            ``ipaddress`` library then handles IPv4/IPv6 prefix maths safely.
        """

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
    """Store every cloud-prefix match found for one input IP address.

    ``matches`` may be empty, contain one prefix, or contain several overlapping
    prefixes.  Keeping all matches is important because provider publications
    can intentionally describe the same address at different levels of detail.
    """

    ip: IPAddress
    matches: tuple[CloudPrefix, ...]

    @property
    def matched(self) -> bool:
        """Return ``True`` when at least one provider prefix contains the IP."""

        return bool(self.matches)

    @property
    def providers(self) -> tuple[str, ...]:
        """Return unique provider names while preserving match order.

        ``dict.fromkeys`` is used as a compact ordered de-duplication technique:
        dictionary keys retain insertion order, so the first occurrence of each
        provider is kept without sorting away the matcher's specificity order.
        """

        return tuple(dict.fromkeys(match.provider for match in self.matches))
