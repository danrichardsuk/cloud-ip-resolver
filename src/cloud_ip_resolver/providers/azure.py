"""Adapter for Microsoft's Azure Public Service Tags publication.

Unlike AWS and GCP, Azure's stable public URL is a download page rather than the
JSON itself.  The live path therefore has two steps: fetch the Microsoft page,
discover the current ``ServiceTags_Public...json`` link, then download that
file.  A saved JSON snapshot can be supplied to skip both network requests for
reproducible parity tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import json
from pathlib import Path
import re
from typing import Any, Mapping
from urllib.request import Request, urlopen

from ..models import CloudPrefix
from .base import ProviderAdapter

AZURE_SERVICE_TAGS_PAGE_URL = "https://www.microsoft.com/en-us/download/details.aspx?id=56519"

# Microsoft changes the actual JSON filename as new weekly publications appear.
# The expression extracts the current download.microsoft.com JSON link from the
# human-facing download page instead of hard-coding a dated filename.
_DOWNLOAD_LINK_RE = re.compile(
    r'href=["\'](https://download\.microsoft\.com/download/[^"\']+ServiceTags_Public[^"\']+\.json)["\']',
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AzureFeed:
    """Represent one parsed Azure Public Service Tags publication."""

    change_number: int | None
    cloud: str | None
    prefixes: tuple[CloudPrefix, ...]

    @property
    def ipv4_count(self) -> int:
        """Return the number of IPv4 prefixes in this publication."""

        return sum(prefix.network.version == 4 for prefix in self.prefixes)

    @property
    def ipv6_count(self) -> int:
        """Return the number of IPv6 prefixes in this publication."""

        return sum(prefix.network.version == 6 for prefix in self.prefixes)


class AzureProvider(ProviderAdapter):
    """Load Azure Service Tags from Microsoft or a saved JSON snapshot."""

    name = "Azure"

    def __init__(
        self,
        *,
        ranges_file: str | Path | None = None,
        download_page_url: str = AZURE_SERVICE_TAGS_PAGE_URL,
        timeout: float = 30.0,
    ) -> None:
        """Configure the Azure Service Tags source.

        Args:
            ranges_file: Optional saved ``ServiceTags_Public.json``. Supplying a
                file avoids live discovery/download and makes tests repeatable.
            download_page_url: Microsoft page used to discover the latest JSON.
            timeout: Maximum seconds for each live HTTP request.
        """

        self.ranges_file = Path(ranges_file) if ranges_file is not None else None
        self.download_page_url = download_page_url
        self.timeout = timeout

    def load_feed(self) -> AzureFeed:
        """Read and parse the configured Azure Service Tags publication."""

        return parse_azure_feed(self._read_payload())

    def load_prefixes(self) -> list[CloudPrefix]:
        """Return normalised prefixes for the generic provider interface."""

        return list(self.load_feed().prefixes)

    def _read_payload(self) -> Mapping[str, Any]:
        """Read Azure JSON from disk or discover/download the current live file.

        Returns:
            Decoded top-level JSON mapping.

        Raises:
            OSError: If local or network data cannot be read.
            ValueError: If the downloaded JSON is not an object.
        """

        if self.ranges_file is not None:
            with self.ranges_file.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        else:
            download_url = self._discover_download_url()
            request = Request(
                download_url,
                headers={"User-Agent": "cloud-ip-resolver/0.6"},
            )
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)

        if not isinstance(payload, dict):
            raise ValueError("Azure Service Tags feed must be a JSON object")
        return payload

    def _discover_download_url(self) -> str:
        """Find the current Service Tags JSON URL on Microsoft's download page.

        Returns:
            Direct ``download.microsoft.com`` link to the dated JSON file.

        Raises:
            ValueError: If Microsoft's page shape changes and the expected JSON
                link can no longer be found.
        """

        request = Request(
            self.download_page_url,
            headers={"User-Agent": "cloud-ip-resolver/0.6"},
        )
        with urlopen(request, timeout=self.timeout) as response:
            page = response.read().decode("utf-8", errors="replace")

        # HTML entities may appear in attributes, so decode them before applying
        # the link expression.
        match = _DOWNLOAD_LINK_RE.search(unescape(page))
        if match is None:
            raise ValueError("Could not find the Azure Service Tags JSON download link")
        return match.group(1)


def parse_azure_feed(payload: Mapping[str, Any]) -> AzureFeed:
    """Translate Azure Service Tags JSON into common ``CloudPrefix`` objects.

    Args:
        payload: Decoded Azure publication.

    Returns:
        ``AzureFeed`` with publication metadata and one prefix object for every
        item in every service tag's ``addressPrefixes`` list.

    Raises:
        ValueError: If the top-level ``values`` collection or an individual tag
            has an unexpected shape.
    """

    records = payload.get("values", [])
    if not isinstance(records, list):
        raise ValueError("Azure Service Tags feed contains an invalid values collection")

    prefixes: list[CloudPrefix] = []
    for record in records:
        prefixes.extend(_parse_service_tag(record))

    return AzureFeed(
        change_number=_optional_int(payload.get("changeNumber")),
        cloud=_optional_string(payload.get("cloud")),
        prefixes=tuple(prefixes),
    )


def _parse_service_tag(record: Any) -> list[CloudPrefix]:
    """Expand one Azure service-tag object into one prefix per address range.

    Args:
        record: Raw item from Azure's top-level ``values`` list.

    Returns:
        List of normalised prefixes sharing the service tag's metadata.

    Raises:
        ValueError: If required tag properties are absent or have invalid types.

    Azure groups many CIDRs under one service tag.  The resolver works at CIDR
    level, so this function intentionally expands one input object into several
    ``CloudPrefix`` objects while copying the tag metadata onto each one.
    """

    if not isinstance(record, dict):
        raise ValueError("Azure service-tag record must be a JSON object")

    name = record.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("Azure service-tag record is missing name")

    properties = record.get("properties")
    if not isinstance(properties, dict):
        raise ValueError(f"Azure service tag {name!r} is missing properties")

    address_prefixes = properties.get("addressPrefixes", [])
    if not isinstance(address_prefixes, list):
        raise ValueError(f"Azure service tag {name!r} has invalid addressPrefixes")

    network_features = properties.get("networkFeatures")
    if network_features is None:
        feature_text = ""
    elif isinstance(network_features, list) and all(
        isinstance(feature, str) for feature in network_features
    ):
        # The legacy CSV stores multiple features in one semicolon-delimited cell.
        feature_text = ";".join(network_features)
    else:
        raise ValueError(f"Azure service tag {name!r} has invalid networkFeatures")

    service = _optional_string(properties.get("systemService"))
    region = _optional_string(properties.get("region"))
    platform = _optional_string(properties.get("platform"))
    tag_change_number = _optional_int(properties.get("changeNumber"))
    record_id = _optional_string(record.get("id"))

    result: list[CloudPrefix] = []
    for cidr in address_prefixes:
        if not isinstance(cidr, str) or not cidr.strip():
            raise ValueError(f"Azure service tag {name!r} contains an invalid prefix")

        result.append(
            CloudPrefix.from_cidr(
                provider="Azure",
                cidr=cidr,
                service=service,
                region=region,
                # ``scope`` holds the service-tag name in the common model.
                scope=name,
                metadata={
                    "name": name,
                    "published_prefix": cidr,
                    "network_features": feature_text,
                    "platform": platform,
                    "service_tag_change_number": tag_change_number,
                    "id": record_id,
                },
            )
        )

    return result


def _optional_string(value: Any) -> str | None:
    """Return a JSON value only when it is a string, otherwise ``None``."""

    return value if isinstance(value, str) else None


def _optional_int(value: Any) -> int | None:
    """Return a real integer while deliberately excluding JSON booleans.

    In Python, ``bool`` is a subclass of ``int``.  The explicit boolean check
    prevents values such as ``true`` being accidentally accepted as change
    number ``1``.
    """

    return value if isinstance(value, int) and not isinstance(value, bool) else None
