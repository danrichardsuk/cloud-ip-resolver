"""Adapter for Amazon Web Services' public ``ip-ranges.json`` feed.

The AWS publication has separate arrays for IPv4 and IPv6 records.  This module
loads either a saved snapshot (useful for parity tests) or the live publication,
validates its basic shape, and converts both arrays into common ``CloudPrefix``
objects for the shared resolver.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from ..models import CloudPrefix
from .base import ProviderAdapter

AWS_IP_RANGES_URL = "https://ip-ranges.amazonaws.com/ip-ranges.json"


@dataclass(frozen=True, slots=True)
class AwsFeed:
    """Represent one parsed AWS range publication and its metadata."""

    sync_token: str | None
    create_date: str | None
    prefixes: tuple[CloudPrefix, ...]

    @property
    def ipv4_count(self) -> int:
        """Return the number of IPv4 prefixes in this publication."""

        return sum(prefix.network.version == 4 for prefix in self.prefixes)

    @property
    def ipv6_count(self) -> int:
        """Return the number of IPv6 prefixes in this publication."""

        return sum(prefix.network.version == 6 for prefix in self.prefixes)


class AwsProvider(ProviderAdapter):
    """Load AWS ranges from the live feed or a saved JSON snapshot."""

    name = "AWS"

    def __init__(
        self,
        *,
        ranges_file: str | Path | None = None,
        url: str = AWS_IP_RANGES_URL,
        timeout: float = 30.0,
    ) -> None:
        """Configure where AWS range data should come from.

        Args:
            ranges_file: Optional local ``ip-ranges.json``. When supplied, no
                network request is made; this is ideal for reproducible testing.
            url: Live AWS feed URL. Exposed mainly to make testing/customisation
                possible without hard-coding the endpoint inside the method.
            timeout: Maximum seconds to wait for the live HTTP request.
        """

        self.ranges_file = Path(ranges_file) if ranges_file is not None else None
        self.url = url
        self.timeout = timeout

    def load_feed(self) -> AwsFeed:
        """Read the configured source and parse it into an ``AwsFeed``."""

        payload = self._read_payload()
        return parse_aws_feed(payload)

    def load_prefixes(self) -> list[CloudPrefix]:
        """Return only normalised prefixes for the generic workflow interface."""

        return list(self.load_feed().prefixes)

    def _read_payload(self) -> Mapping[str, Any]:
        """Read raw AWS JSON from disk or HTTP and ensure it is an object.

        Returns:
            Mapping containing the decoded JSON publication.

        Raises:
            OSError: If a local file or network request cannot be read.
            ValueError: If the decoded top-level JSON value is not an object.
        """

        if self.ranges_file is not None:
            with self.ranges_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            request = Request(
                self.url,
                headers={"User-Agent": "cloud-ip-resolver/0.6"},
            )
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)

        if not isinstance(payload, dict):
            raise ValueError("AWS range feed must be a JSON object")
        return payload


def parse_aws_feed(payload: Mapping[str, Any]) -> AwsFeed:
    """Normalise an AWS ``ip-ranges.json`` payload.

    Args:
        payload: Already-decoded JSON mapping.

    Returns:
        ``AwsFeed`` containing publication metadata and all IPv4/IPv6 prefixes.

    Raises:
        ValueError: If either AWS prefix collection has an unexpected type or a
            child record is malformed.

    The legacy PowerShell script only iterated ``prefixes``.  Explicitly parsing
    ``ipv6_prefixes`` here is what gives the Python implementation full IPv6
    support.
    """

    prefixes: list[CloudPrefix] = []

    ipv4_records = payload.get("prefixes", [])
    ipv6_records = payload.get("ipv6_prefixes", [])
    if not isinstance(ipv4_records, list) or not isinstance(ipv6_records, list):
        raise ValueError("AWS range feed contains invalid prefix collections")

    for record in ipv4_records:
        prefixes.append(_parse_record(record, cidr_key="ip_prefix"))

    for record in ipv6_records:
        prefixes.append(_parse_record(record, cidr_key="ipv6_prefix"))

    return AwsFeed(
        sync_token=_optional_string(payload.get("syncToken")),
        create_date=_optional_string(payload.get("createDate")),
        prefixes=tuple(prefixes),
    )


def _parse_record(record: Any, *, cidr_key: str) -> CloudPrefix:
    """Convert one AWS IPv4 or IPv6 JSON record into ``CloudPrefix``.

    Args:
        record: Raw record from one of AWS's prefix arrays.
        cidr_key: ``ip_prefix`` for IPv4 or ``ipv6_prefix`` for IPv6.

    Returns:
        Normalised provider-independent prefix.

    Raises:
        ValueError: If the record is not an object or its CIDR field is missing.
    """

    if not isinstance(record, dict):
        raise ValueError("AWS prefix record must be a JSON object")

    cidr = record.get(cidr_key)
    if not isinstance(cidr, str) or not cidr.strip():
        raise ValueError(f"AWS prefix record is missing {cidr_key}")

    return CloudPrefix.from_cidr(
        provider="AWS",
        cidr=cidr,
        service=_optional_string(record.get("service")),
        region=_optional_string(record.get("region")),
        metadata={
            # Network border group is AWS-specific, so it lives in metadata and
            # is surfaced only in AWS-specific/combined output columns.
            "network_border_group": _optional_string(
                record.get("network_border_group")
            )
        },
    )


def _optional_string(value: Any) -> str | None:
    """Return a JSON value only when it is already a string, otherwise ``None``."""

    return value if isinstance(value, str) else None
