"""Cloud IP Resolver core package."""

from .matcher import PrefixMatcher
from .models import CloudPrefix, Resolution
from .resolver import Resolver
from .workflow import MultiProviderResult, MultiProviderWorkflow, ProviderRangeSummary

__all__ = [
    "CloudPrefix",
    "MultiProviderResult",
    "MultiProviderWorkflow",
    "PrefixMatcher",
    "ProviderRangeSummary",
    "Resolution",
    "Resolver",
]
__version__ = "0.5.0"
