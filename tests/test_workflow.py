"""Integration-style tests for the unified multi-provider workflow and CLI.

Unlike provider parser tests, these checks use tiny in-memory stub providers to
exercise the shared workflow across several providers at once.  They protect
input order, duplicates, overlapping matches, provider summary counts, the
combined analyst-facing CSV schema, and the real ``all`` CLI command.
"""

import csv
from pathlib import Path

import pytest

from cloud_ip_resolver.cli import build_parser, main
from cloud_ip_resolver.io import COMBINED_OUTPUT_FIELDS, write_combined_matches_csv
from cloud_ip_resolver.models import CloudPrefix
from cloud_ip_resolver.workflow import MultiProviderWorkflow

FIXTURES = Path(__file__).parent / "fixtures"


class StubProvider:
    """Minimal provider used to test workflows without network/provider parsing.

    The production workflow only requires a ``name`` and ``load_prefixes``
    method.  This intentionally small stub demonstrates that interface clearly
    and lets tests choose exact synthetic ranges for each scenario.
    """

    def __init__(self, name, prefixes):
        """Store a provider display name and deterministic prefix collection."""

        self.name = name
        self._prefixes = prefixes

    def load_prefixes(self):
        """Return a new list so callers cannot mutate the stub's stored input."""

        return list(self._prefixes)


def _synthetic_workflow():
    """Build a three-provider workflow containing deliberate test edge cases.

    Returns:
        ``MultiProviderWorkflow`` with:
        * overlapping AWS/Azure IPv4 ranges;
        * provider-only IPv4 ranges for Azure and GCP; and
        * one GCP IPv6 range.

    Keeping this setup in one helper means the workflow/output tests exercise
    exactly the same synthetic provider landscape.
    """

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
    """Exercise overlap, provider-only, unmatched, duplicate and IPv6 inputs.

    The expected provider tuples also verify most-specific ordering: the first
    address is inside Azure /25 and AWS /24, so Azure appears first.
    """

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
    """Protect the combined schema, row order and provider-specific namespaces.

    This is the key analyst-facing contract test.  It verifies that Azure values
    only populate ``Azure_*`` fields, AWS metadata only populates ``AWS_*``, and
    GCP scope only populates ``GCP_Scope``.  It also confirms unmatched IPs are
    omitted and duplicate inputs create duplicate output groups.
    """

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

    # Azure row: Azure-specific values are populated, AWS/GCP-specific cells blank.
    assert rows[0]["Azure_ServiceTagName"] == "Storage.WestEurope"
    assert rows[0]["Azure_NetworkFeatures"] == "API;NSG"
    assert rows[0]["AWS_NetworkBorderGroup"] == ""
    assert rows[0]["GCP_Scope"] == ""

    # AWS row: only the AWS-specific metadata column is populated.
    assert rows[1]["AWS_NetworkBorderGroup"] == "eu-west-2"
    assert rows[1]["Azure_ServiceTagName"] == ""
    assert rows[1]["GCP_Scope"] == ""

    # GCP row: scope is explicitly namespaced rather than sharing an ambiguous column.
    gcp_row = next(row for row in rows if row["Provider"] == "GCP")
    assert gcp_row["GCP_Scope"] == "europe-west2"
    assert gcp_row["Azure_ServiceTagName"] == ""

    assert all(row["IPAddress"] != "192.0.2.1" for row in rows)


def test_all_cli_uses_saved_provider_snapshots(tmp_path: Path) -> None:
    """Run the real ``all`` command in-process with all three saved fixtures.

    This exercises parser -> input reader -> provider adapters -> workflow ->
    combined writer as one end-to-end path, without depending on the network.
    """

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

    # Spot-check that the end-to-end command also uses the new namespaced fields.
    assert any(row["AWS_NetworkBorderGroup"] for row in rows if row["Provider"] == "AWS")
    assert any(row["Azure_ServiceTagName"] for row in rows if row["Provider"] == "Azure")
    assert any(row["GCP_Scope"] for row in rows if row["Provider"] == "GCP")


def test_cli_keeps_provider_commands_and_adds_all() -> None:
    """Ensure the unified command is additive and old provider CLI syntax still parses."""

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
    """Reject accidental duplicate provider adapters before they duplicate output."""

    provider = StubProvider("AWS", [])
    with pytest.raises(ValueError, match="Duplicate cloud providers"):
        MultiProviderWorkflow([provider, provider])
