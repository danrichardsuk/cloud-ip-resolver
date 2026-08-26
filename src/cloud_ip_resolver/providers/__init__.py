"""Cloud-provider range sources."""

from .aws import AWS_IP_RANGES_URL, AwsFeed, AwsProvider
from .azure import AZURE_SERVICE_TAGS_PAGE_URL, AzureFeed, AzureProvider
from .base import ProviderAdapter
from .gcp import GCP_CLOUD_RANGES_URL, GcpFeed, GcpProvider

__all__ = [
    "AWS_IP_RANGES_URL",
    "AwsFeed",
    "AwsProvider",
    "AZURE_SERVICE_TAGS_PAGE_URL",
    "AzureFeed",
    "AzureProvider",
    "GCP_CLOUD_RANGES_URL",
    "GcpFeed",
    "GcpProvider",
    "ProviderAdapter",
]
