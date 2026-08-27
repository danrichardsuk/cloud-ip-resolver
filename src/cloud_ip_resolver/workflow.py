"""Reusable multi-provider resolution workflow for the CLI and desktop UI."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from .models import CloudPrefix, Resolution
from .providers.base import ProviderAdapter
from .resolver import Resolver


@dataclass(frozen=True, slots=True)
class ProviderRangeSummary:
    """Prefix counts loaded from one provider adapter."""

    provider: str
    prefix_count: int
    ipv4_count: int
    ipv6_count: int


@dataclass(frozen=True, slots=True)
class MultiProviderResult:
    """Resolution output plus provider loading statistics."""

    provider_summaries: tuple[ProviderRangeSummary, ...]
    resolutions: tuple[Resolution, ...]

    @property
    def matched_input_count(self) -> int:
        return sum(resolution.matched for resolution in self.resolutions)

    @property
    def match_count(self) -> int:
        return sum(len(resolution.matches) for resolution in self.resolutions)


class MultiProviderWorkflow:
    """Load multiple provider adapters and resolve one shared input list."""

    def __init__(self, providers: Iterable[ProviderAdapter]) -> None:
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
        """Load all configured prefixes once and resolve values in input order."""

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
