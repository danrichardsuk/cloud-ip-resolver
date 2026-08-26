"""Interface implemented by each cloud provider adapter."""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import CloudPrefix


class ProviderAdapter(ABC):
    """Translate one provider's published range data into CloudPrefix objects."""

    name: str

    @abstractmethod
    def load_prefixes(self) -> list[CloudPrefix]:
        """Fetch and return the provider's current published IP ranges."""
