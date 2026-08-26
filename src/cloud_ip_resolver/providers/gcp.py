"""Google Cloud public IP range provider adapter."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping
from urllib.request import Request, urlopen

from ..models import CloudPrefix
from .base import ProviderAdapter

GCP_CLOUD_RANGES_URL = "https://www.gstatic.com/ipranges/cloud.json"


@dataclass(frozen=True, slots=True)
class GcpFeed:
    """One parsed Google Cloud cloud.json publication."""

    sync_token: str | None
    creation_time: str | None
    prefixes: tuple[CloudPrefix, ...]

    @property
    def ipv4_count(self) -> int:
        return sum(prefix.network.version == 4 for prefix in self.prefixes)

    @property
    def ipv6_count(self) -> int:
        return sum(prefix.network.version == 6 for prefix in self.prefixes)


class GcpProvider(ProviderAdapter):
    """Load Google Cloud ranges from the live cloud.json feed or a saved file."""

    name = "GCP"

    def __init__(
        self,
        *,
        ranges_file: str | Path | None = None,
        url: str = GCP_CLOUD_RANGES_URL,
        timeout: float = 30.0,
    ) -> None:
        self.ranges_file = Path(ranges_file) if ranges_file is not None else None
        self.url = url
        self.timeout = timeout

    def load_feed(self) -> GcpFeed:
        return parse_gcp_feed(self._read_payload())

    def load_prefixes(self) -> list[CloudPrefix]:
        return list(self.load_feed().prefixes)

    def _read_payload(self) -> Mapping[str, Any]:
        if self.ranges_file is not None:
            with self.ranges_file.open("r", encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        else:
            request = Request(
                self.url,
                headers={"User-Agent": "cloud-ip-resolver/0.4"},
            )
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)

        if not isinstance(payload, dict):
            raise ValueError("Google Cloud range feed must be a JSON object")
        return payload


def parse_gcp_feed(payload: Mapping[str, Any]) -> GcpFeed:
    """Translate Google Cloud cloud.json into the common prefix model."""

    records = payload.get("prefixes", [])
    if not isinstance(records, list):
        raise ValueError("Google Cloud range feed contains an invalid prefixes collection")

    prefixes = tuple(_parse_record(record) for record in records)
    return GcpFeed(
        sync_token=_optional_string(payload.get("syncToken")),
        creation_time=_optional_string(payload.get("creationTime")),
        prefixes=prefixes,
    )


def _parse_record(record: Any) -> CloudPrefix:
    if not isinstance(record, dict):
        raise ValueError("Google Cloud prefix record must be a JSON object")

    ipv4 = record.get("ipv4Prefix")
    ipv6 = record.get("ipv6Prefix")
    has_ipv4 = isinstance(ipv4, str) and bool(ipv4.strip())
    has_ipv6 = isinstance(ipv6, str) and bool(ipv6.strip())
    if has_ipv4 == has_ipv6:
        raise ValueError(
            "Google Cloud prefix record must contain exactly one of ipv4Prefix or ipv6Prefix"
        )

    cidr = ipv4 if has_ipv4 else ipv6
    assert isinstance(cidr, str)
    return CloudPrefix.from_cidr(
        provider="GCP",
        cidr=cidr,
        service=_optional_string(record.get("service")),
        scope=_optional_string(record.get("scope")),
        metadata={"published_prefix": cidr},
    )


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
