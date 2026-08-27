"""Public package API for Cloud IP Resolver.

This module is deliberately small. It re-exports the main classes that a
caller (for example the CLI, desktop GUI, or another Python project) is most
likely to use. Keeping these names here gives users one predictable place to
import the core resolver concepts from.
"""

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

# The version is kept in code as well as pyproject.toml so a packaged
# application can display it without having to parse project configuration.
__version__ = "0.7.2"
