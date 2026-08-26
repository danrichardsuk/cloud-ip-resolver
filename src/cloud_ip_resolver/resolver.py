"""Provider-independent IP resolution engine."""

from __future__ import annotations

from collections.abc import Iterable
from ipaddress import ip_address

from .matcher import PrefixMatcher
from .models import CloudPrefix, Resolution


class Resolver:
    """Resolve one or many addresses against a set of cloud prefixes."""

    def __init__(self, prefixes: Iterable[CloudPrefix]) -> None:
        self._matcher = PrefixMatcher(prefixes)

    def resolve_one(self, value: str) -> Resolution:
        address = ip_address(value.strip())
        return Resolution(ip=address, matches=self._matcher.find_all(address))

    def resolve_many(self, values: Iterable[str]) -> list[Resolution]:
        """Resolve input values in order, preserving duplicate rows."""

        return [self.resolve_one(value) for value in values]
