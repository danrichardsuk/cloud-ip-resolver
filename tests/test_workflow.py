import csv
from pathlib import Path

import pytest

from cloud_ip_resolver.cli import build_parser, main
from cloud_ip_resolver.io import COMBINED_OUTPUT_FIELDS, write_combined_matches_csv
from cloud_ip_resolver.models import CloudPrefix
from cloud_ip_resolver.workflow import MultiProviderWorkflow

FIXTURES = Path(__file__).parent / "fixtures"


class StubProvider:
    def __init__(self, name, prefixes):
        self.name = name
        self._prefixes = prefixes

    def load_prefixes(self):
        return list(self._prefixes)


def _synthetic_workflow():
    return MultiProviderWorkflow(
        [
            StubProvider(
                "AWS",
                [
                    CloudPrefix.from_cidr(
                        provider="AWS",
                        cidr="198.51.100.0/24",
                        service="EC2",
                        region="eu-west-2",
                        metadata={"network_border_group": "eu-west-2"},
                    )
                ],
            ),
            StubProvider(
                "Azure",
                [
                    CloudPrefix.from_cidr(
                        provider="Azure",
                        cidr="198.51.100.0/25",
                        service="Storage",
                        region="westeurope",
                        scope="Storage.WestEurope",
                        metadata={
                            "published_prefix": "198.51.100.0/25",
                            "network_features": "API;NSG",
                        },
                    ),
                    CloudPrefix.from_cidr(
                        provider="Azure",
                        cidr="20.0.0.0/24",
                        service="AzureCloud",
                        region="westeurope",
                        scope="AzureCloud.WestEurope",
                    ),
                ],
            ),
            StubProvider(
                "GCP",
                [
                    CloudPrefix.from_cidr(
                        provider="GCP",
                        cidr="203.0.113.0/24",
                        service="Google Cloud",
                        scope="europe-west2",
                        metadata={"published_prefix": "203.0.113.0/24"},
                    ),
                    CloudPrefix.from_cidr(
                        provider="GCP",
                        cidr="2001:db8:1::/48",
                        service="Google Cloud",
                        scope="global",
                    ),
                ],
            ),
        ]
    )


def test_multi_provider_workflow_handles_all_cases() -> None:
    values = [
        "198.51.100.10",
        "198.51.100.200",
        "20.0.0.5",
        "203.0.113.5",
        "192.0.2.1",
        "198.51.100.10",
        "2001:db8:1::1",
    ]
    result = _synthetic_workflow().resolve_many(values)

    assert [str(item.ip) for item in result.resolutions] == values
    assert [item.providers for item in result.resolutions] == [
        ("Azure", "AWS"),
        ("AWS",),
        ("Azure",),
        ("GCP",),
        (),
        ("Azure", "AWS"),
        ("GCP",),
    ]
    assert result.matched_input_count == 6
    assert result.match_count == 8

    summaries = {summary.provider: summary for summary in result.provider_summaries}
    assert summaries["AWS"].prefix_count == 1
    assert summaries["Azure"].ipv4_count == 2
    assert summaries["GCP"].ipv6_count == 1


def test_combined_output_schema_and_order(tmp_path: Path) -> None:
    values = [
        "198.51.100.10",
        "198.51.100.200",
        "20.0.0.5",
        "203.0.113.5",
        "192.0.2.1",
        "198.51.100.10",
        "2001:db8:1::1",
    ]
    result = _synthetic_workflow().resolve_many(values)
    output = tmp_path / "all.csv"

    rows_written = write_combined_matches_csv(output, result.resolutions)

    with output.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert rows_written == 8
    assert tuple(reader.fieldnames or ()) == COMBINED_OUTPUT_FIELDS
    assert [(row["IPAddress"], row["Provider"]) for row in rows] == [
        ("198.51.100.10", "Azure"),
        ("198.51.100.10", "AWS"),
        ("198.51.100.200", "AWS"),
        ("20.0.0.5", "Azure"),
        ("203.0.113.5", "GCP"),
        ("198.51.100.10", "Azure"),
        ("198.51.100.10", "AWS"),
        ("2001:db8:1::1", "GCP"),
    ]
    assert rows[0]["Scope"] == "Storage.WestEurope"
    assert rows[0]["NetworkFeatures"] == "API;NSG"
    assert rows[1]["NetworkBorderGroup"] == "eu-west-2"
    assert all(row["IPAddress"] != "192.0.2.1" for row in rows)


def test_all_cli_uses_saved_provider_snapshots(tmp_path: Path) -> None:
    input_path = tmp_path / "input.csv"
    output_path = tmp_path / "combined.csv"
    input_path.write_text(
        "IPAddress\n"
        "198.51.100.10\n"
        "20.1.2.3\n"
        "34.80.10.20\n"
        "192.0.2.1\n"
        "2001:db8:1234::1\n"
        "2001:db8:3fff::1\n"
        "2600:1900:1000::1\n",
        encoding="utf-8",
    )

    exit_code = main(
        [
            "all",
            str(input_path),
            "-o",
            str(output_path),
            "--aws-ranges-file",
            str(FIXTURES / "aws_ip_ranges.json"),
            "--azure-ranges-file",
            str(FIXTURES / "azure_service_tags.json"),
            "--gcp-ranges-file",
            str(FIXTURES / "gcp_cloud.json"),
        ]
    )

    assert exit_code == 0
    with output_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == 9
    assert {row["Provider"] for row in rows} == {"AWS", "Azure", "GCP"}
    assert all(row["IPAddress"] != "192.0.2.1" for row in rows)


def test_cli_keeps_provider_commands_and_adds_all() -> None:
    parser = build_parser()
    for command in ("aws", "azure", "gcp"):
        args = parser.parse_args([command, "input.csv"])
        assert args.command == command
        assert args.ranges_file is None

    args = parser.parse_args(
        [
            "all",
            "input.csv",
            "--aws-ranges-file",
            "aws.json",
            "--azure-ranges-file",
            "azure.json",
            "--gcp-ranges-file",
            "gcp.json",
        ]
    )
    assert args.command == "all"
    assert args.output == Path("output_all.csv")
    assert args.aws_ranges_file == Path("aws.json")


def test_duplicate_providers_are_rejected() -> None:
    provider = StubProvider("AWS", [])
    with pytest.raises(ValueError, match="Duplicate cloud providers"):
        MultiProviderWorkflow([provider, provider])
