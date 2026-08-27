"""Tests for the per-provider match statistics shown by the combined CLI.

The combined workflow has two useful match concepts for each provider:
``matched input rows`` counts an input row once when that provider matched it,
while ``output match rows`` counts every overlapping prefix that will be written
to the CSV.  These tests protect both the reusable result methods and the
human-readable terminal summary.
"""

from ipaddress import ip_address

from cloud_ip_resolver.cli import _print_provider_match_summary
from cloud_ip_resolver.models import CloudPrefix, Resolution
from cloud_ip_resolver.workflow import MultiProviderResult, ProviderRangeSummary


def _sample_result() -> MultiProviderResult:
    """Create a small result where AWS deliberately has overlapping matches.

    The first IP matches two AWS prefixes and one Azure prefix.  The second IP
    matches one AWS prefix, the third matches GCP, and the fourth is unmatched.
    This makes the difference between input-row counts and output-row counts
    visible without relying on live provider data.
    """

    aws_broad = CloudPrefix.from_cidr(
        provider="AWS", cidr="198.51.100.0/24", service="AMAZON"
    )
    aws_specific = CloudPrefix.from_cidr(
        provider="AWS", cidr="198.51.100.0/25", service="EC2"
    )
    azure = CloudPrefix.from_cidr(
        provider="Azure", cidr="198.51.100.0/25", service="Storage"
    )
    gcp = CloudPrefix.from_cidr(
        provider="GCP", cidr="203.0.113.0/24", service="Google Cloud"
    )

    return MultiProviderResult(
        provider_summaries=(
            ProviderRangeSummary("AWS", 2, 2, 0),
            ProviderRangeSummary("Azure", 1, 1, 0),
            ProviderRangeSummary("GCP", 1, 1, 0),
        ),
        resolutions=(
            Resolution(
                ip=ip_address("198.51.100.10"),
                matches=(aws_specific, aws_broad, azure),
            ),
            Resolution(
                ip=ip_address("198.51.100.200"),
                matches=(aws_broad,),
            ),
            Resolution(
                ip=ip_address("203.0.113.5"),
                matches=(gcp,),
            ),
            Resolution(ip=ip_address("192.0.2.1"), matches=()),
        ),
    )


def test_multi_provider_result_counts_matches_per_provider() -> None:
    """Distinguish unique matched inputs from individual output rows by provider."""

    result = _sample_result()

    assert result.matched_input_count == 3
    assert result.match_count == 5

    assert result.matched_input_count_for("AWS") == 2
    assert result.match_count_for("AWS") == 3

    assert result.matched_input_count_for("Azure") == 1
    assert result.match_count_for("Azure") == 1

    assert result.matched_input_count_for("GCP") == 1
    assert result.match_count_for("GCP") == 1

    # Asking about a provider that did not participate is harmless and returns 0.
    assert result.matched_input_count_for("Unknown") == 0
    assert result.match_count_for("Unknown") == 0


def test_cli_prints_provider_match_summary(capsys) -> None:
    """Show both per-provider numbers in a compact, analyst-friendly format."""

    _print_provider_match_summary(_sample_result())

    assert capsys.readouterr().out.splitlines() == [
        "Provider matches:",
        "  AWS: matched input rows 2; output match rows 3",
        "  Azure: matched input rows 1; output match rows 1",
        "  GCP: matched input rows 1; output match rows 1",
    ]
