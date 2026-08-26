"""AWS public IP range provider adapter."""

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
    """One parsed AWS ip-ranges.json publication."""

    sync_token: str | None
    create_date: str | None
    prefixes: tuple[CloudPrefix, ...]

    @property
    def ipv4_count(self) -> int:
        return sum(prefix.network.version == 4 for prefix in self.prefixes)

    @property
    def ipv6_count(self) -> int:
        return sum(prefix.network.version == 6 for prefix in self.prefixes)


class AwsProvider(ProviderAdapter):
    """Load AWS ranges from the live feed or a saved ip-ranges.json file."""

    name = "AWS"

    def __init__(
        self,
        *,
        ranges_file: str | Path | None = None,
        url: str = AWS_IP_RANGES_URL,
        timeout: float = 30.0,
    ) -> None:
        self.ranges_file = Path(ranges_file) if ranges_file is not None else None
        self.url = url
        self.timeout = timeout

    def load_feed(self) -> AwsFeed:
        payload = self._read_payload()
        return parse_aws_feed(payload)

    def load_prefixes(self) -> list[CloudPrefix]:
        return list(self.load_feed().prefixes)

    def _read_payload(self) -> Mapping[str, Any]:
        if self.ranges_file is not None:
            with self.ranges_file.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
        else:
            request = Request(
                self.url,
                headers={"User-Agent": "cloud-ip-resolver/0.2"},
            )
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.load(response)

        if not isinstance(payload, dict):
            raise ValueError("AWS range feed must be a JSON object")
        return payload


def parse_aws_feed(payload: Mapping[str, Any]) -> AwsFeed:
    """Translate an AWS ip-ranges.json payload into the common model."""

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
            "network_border_group": _optional_string(
                record.get("network_border_group")
            )
        },
    )


def _optional_string(value: Any) -> str | None:
    return value if isinstance(value, str) else None
