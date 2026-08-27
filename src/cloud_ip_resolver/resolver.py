"""Provider-independent orchestration around the prefix matcher.

The resolver is intentionally thin: provider adapters prepare the data,
``PrefixMatcher`` performs network matching, and this class turns those matches
into ``Resolution`` records while preserving the caller's input order.
"""

from __future__ import annotations

from collections.abc import Iterable
from ipaddress import ip_address

from .matcher import PrefixMatcher
from .models import CloudPrefix, Resolution


class Resolver:
    """Resolve one or many textual IP addresses against a prepared prefix set."""

    def __init__(self, prefixes: Iterable[CloudPrefix]) -> None:
        """Create and retain one matcher for all subsequent address lookups.

        Args:
            prefixes: Normalised ranges from one provider or several providers.

        Building the matcher once is important for batch performance: the costly
        indexing work is not repeated for every row of the input CSV.
        """

        self._matcher = PrefixMatcher(prefixes)

    def resolve_one(self, value: str) -> Resolution:
        """Resolve one textual IP and return all matching cloud prefixes.

        Args:
            value: IPv4 or IPv6 text. Leading/trailing whitespace is ignored.

        Returns:
            A ``Resolution`` containing the parsed address and all matches.

        Raises:
            ValueError: If ``value`` is not a valid IPv4 or IPv6 address.
        """

        address = ip_address(value.strip())
        return Resolution(ip=address, matches=self._matcher.find_all(address))

    def resolve_many(self, values: Iterable[str]) -> list[Resolution]:
        """Resolve an input sequence without reordering or removing duplicates.

        Args:
            values: Iterable of textual IPv4/IPv6 values.

        Returns:
            One ``Resolution`` per input value, in the same order. Duplicate
            inputs deliberately produce duplicate resolution records because the
            CSV tools preserve row-level semantics.
        """

        return [self.resolve_one(value) for value in values]
