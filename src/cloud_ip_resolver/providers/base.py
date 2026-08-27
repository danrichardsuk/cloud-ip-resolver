"""Abstract interface shared by cloud-provider range adapters.

The rest of the application should not need to know how a provider publishes
its data.  Any adapter that implements ``load_prefixes`` can participate in the
same resolver and multi-provider workflow.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CloudPrefix


class ProviderAdapter(ABC):
    """Define the minimum contract required from a cloud provider adapter."""

    # Concrete adapters expose a short display name used in output and summaries.
    name: str

    @abstractmethod
    def load_prefixes(self) -> list[CloudPrefix]:
        """Load and normalise the provider's published address ranges.

        Returns:
            A list of provider records converted to common ``CloudPrefix``
            objects. Implementations may read a saved snapshot or fetch live data.
        """
