"""Headless tests for the analyst-facing desktop presentation layer."""

from ipaddress import ip_address
from pathlib import Path

from cloud_ip_resolver.desktop import format_run_summary
from cloud_ip_resolver.gui import GuiRunRequest, GuiRunResult
from cloud_ip_resolver.io import InputBatch, InvalidInput
from cloud_ip_resolver.models import CloudPrefix, Resolution
from cloud_ip_resolver.workflow import MultiProviderResult, ProviderRangeSummary


def _result() -> GuiRunResult:
    """Create a small result containing overlap so the terminology is meaningful."""

    aws_broad = CloudPrefix.from_cidr(
        provider="AWS", cidr="198.51.100.0/24", service="AMAZON"
    )
    aws_specific = CloudPrefix.from_cidr(
        provider="AWS", cidr="198.51.100.0/25", service="EC2"
    )
    gcp = CloudPrefix.from_cidr(
        provider="GCP", cidr="203.0.113.0/24", service="Google Cloud"
    )
    workflow = MultiProviderResult(
        provider_summaries=(
            ProviderRangeSummary("AWS", 2, 2, 0),
            ProviderRangeSummary("GCP", 1, 1, 0),
        ),
        resolutions=(
            Resolution(ip_address("198.51.100.10"), (aws_specific, aws_broad)),
            Resolution(ip_address("203.0.113.5"), (gcp,)),
        ),
    )
    return GuiRunResult(
        request=GuiRunRequest(Path("input.csv"), Path("output.csv"), ("AWS", "GCP")),
        input_batch=InputBatch(
            values=("198.51.100.10", "203.0.113.5"),
            invalid=(InvalidInput(4, "0", "not a valid IP address"),),
        ),
        workflow_result=workflow,
        rows_written=3,
        elapsed_seconds=1.25,
    )


def test_results_explain_match_terminology() -> None:
    """Explain rows versus CIDR matches without implying IPs are deduplicated."""

    summary = format_run_summary(_result())

    assert "ABOUT THESE RESULTS" in summary
    assert "Matched IP rows = input rows with at least one published cloud CIDR match." in summary
    assert "CIDR matches = individual IP-to-prefix matches written to the output CSV." in summary
    assert "provider counts can overlap" in summary


def test_provider_and_overall_counts_use_contextual_names() -> None:
    """Use the clearer labels everywhere the user sees match counts."""

    summary = format_run_summary(_result())

    assert "AWS: 1 matched IP rows; 2 CIDR matches" in summary
    assert "GCP: 1 matched IP rows; 1 CIDR matches" in summary
    assert "Matched IP rows: 2" in summary
    assert "CIDR matches: 3" in summary
    assert "matched input rows" not in summary.lower()
    assert "output match rows" not in summary.lower()
