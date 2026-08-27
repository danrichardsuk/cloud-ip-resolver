"""Reusable multi-provider workflow for the CLI and future desktop UI.

This layer answers a higher-level question than ``Resolver``: "which provider
feeds should be loaded for this run?"  It combines their normalised prefixes,
resolves one shared list of IPs, and returns provider loading statistics.  The
GUI can therefore reuse the same workflow without duplicating business logic.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import CloudPrefix, Resolution
from .providers.base import ProviderAdapter
from .resolver import Resolver


@dataclass(frozen=True, slots=True)
class ProviderRangeSummary:
    """Summarise how many IPv4/IPv6 prefixes one adapter loaded.

    These counts are primarily diagnostic information for the CLI/GUI.  They
    help a user confirm which source was loaded and roughly how much data was
    processed without exposing provider-specific feed internals.
    """

    provider: str
    prefix_count: int
    ipv4_count: int
    ipv6_count: int


@dataclass(frozen=True, slots=True)
class MultiProviderResult:
    """Bundle multi-provider resolutions with feed-loading statistics."""

    provider_summaries: tuple[ProviderRangeSummary, ...]
    resolutions: tuple[Resolution, ...]

    @property
    def matched_input_count(self) -> int:
        """Count input rows that matched at least one published cloud range."""

        return sum(resolution.matched for resolution in self.resolutions)

    @property
    def match_count(self) -> int:
        """Count output matches, including overlaps and duplicate input rows."""

        return sum(len(resolution.matches) for resolution in self.resolutions)


class MultiProviderWorkflow:
    """Load multiple provider adapters and resolve one common list of IPs."""

    def __init__(self, providers: Iterable[ProviderAdapter]) -> None:
        """Validate and retain the providers that will participate in a run.

        Args:
            providers: Adapter instances such as ``AwsProvider`` and
                ``AzureProvider``. A smaller subset is also valid.

        Raises:
            ValueError: If no providers are supplied or a provider name appears
                more than once. Duplicate provider names would otherwise create
                confusing duplicate rows and summaries.
        """

        self.providers = tuple(providers)
        if not self.providers:
            raise ValueError("At least one cloud provider is required")

        names = [provider.name for provider in self.providers]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(
                "Duplicate cloud providers are not allowed: " + ", ".join(duplicates)
            )

    def resolve_many(self, values: Iterable[str]) -> MultiProviderResult:
        """Load each feed once, combine its prefixes, and resolve all input rows.

        Args:
            values: Textual IPv4/IPv6 values to check against every configured
                provider.

        Returns:
            ``MultiProviderResult`` containing one resolution per input row plus
            prefix-count summaries for each provider.

        Notes:
            Prefixes are deliberately combined before constructing ``Resolver``.
            That gives us one shared matcher rather than running three separate
            full passes over the input list.
        """

        prefixes: list[CloudPrefix] = []
        summaries: list[ProviderRangeSummary] = []

        for provider in self.providers:
            loaded = tuple(provider.load_prefixes())
            prefixes.extend(loaded)
            summaries.append(
                ProviderRangeSummary(
                    provider=provider.name,
                    prefix_count=len(loaded),
                    ipv4_count=sum(prefix.network.version == 4 for prefix in loaded),
                    ipv6_count=sum(prefix.network.version == 6 for prefix in loaded),
                )
            )

        resolutions = tuple(Resolver(prefixes).resolve_many(values))
        return MultiProviderResult(
            provider_summaries=tuple(summaries),
            resolutions=resolutions,
        )
