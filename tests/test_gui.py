"""Headless tests for the desktop GUI's reusable execution helpers.

These tests deliberately avoid constructing a Tk window. They exercise request
validation, provider selection, combined output generation, summary formatting,
and small pieces of UI state behaviour using deterministic stubs.
"""

import csv
from pathlib import Path

import pytest

from cloud_ip_resolver.gui import (
    CloudIpResolverApp,
    GuiRunRequest,
    SUMMARY_SEPARATOR,
    default_output_path,
    format_completion_status,
    format_run_summary,
    normalise_provider_names,
    run_resolution,
    validate_run_request,
)
from cloud_ip_resolver.models import CloudPrefix


class StubProvider:
    """Tiny provider adapter returning prefixes supplied by the test."""

    def __init__(self, name: str, prefixes) -> None:
        """Store the provider name and deterministic prefixes."""

        self.name = name
        self._prefixes = tuple(prefixes)

    def load_prefixes(self):
        """Return a fresh list matching the production adapter contract."""

        return list(self._prefixes)


def _builders():
    """Return zero-argument builders for AWS/GCP plus a guard Azure builder."""

    aws_prefixes = [
        CloudPrefix.from_cidr(
            provider="AWS",
            cidr="198.51.100.0/24",
            service="AMAZON",
            region="eu-west-2",
            metadata={"network_border_group": "eu-west-2"},
        ),
        CloudPrefix.from_cidr(
            provider="AWS",
            cidr="198.51.100.0/25",
            service="EC2",
            region="eu-west-2",
            metadata={"network_border_group": "eu-west-2"},
        ),
    ]
    gcp_prefixes = [
        CloudPrefix.from_cidr(
            provider="GCP",
            cidr="203.0.113.0/24",
            service="Google Cloud",
            scope="europe-west2",
        )
    ]

    def azure_should_not_be_called():
        """Fail loudly if provider selection accidentally includes Azure."""

        raise AssertionError("Azure builder should not be called")

    return {
        "AWS": lambda: StubProvider("AWS", aws_prefixes),
        "Azure": azure_should_not_be_called,
        "GCP": lambda: StubProvider("GCP", gcp_prefixes),
    }


def test_provider_names_are_validated_and_normalised() -> None:
    """Keep selected providers unique and in the app's standard display order."""

    assert normalise_provider_names(("GCP", "AWS", "GCP")) == ("AWS", "GCP")

    with pytest.raises(ValueError, match="Select at least one"):
        normalise_provider_names(())
    with pytest.raises(ValueError, match="Unknown cloud provider"):
        normalise_provider_names(("AWS", "OtherCloud"))


def test_default_output_is_next_to_input() -> None:
    """Make the initial output location predictable for an analyst-selected CSV."""

    source = Path("C:/example/input.csv")
    assert default_output_path(source) == Path("C:/example/output_all.csv")


def test_request_validation_rejects_missing_input_and_no_providers(tmp_path: Path) -> None:
    """Catch common form mistakes before downloading provider feeds."""

    missing = GuiRunRequest(
        input_path=tmp_path / "missing.csv",
        output_path=tmp_path / "out.csv",
        providers=("AWS",),
    )
    with pytest.raises(ValueError, match="does not exist"):
        validate_run_request(missing)

    source = tmp_path / "input.csv"
    source.write_text("IPAddress\n198.51.100.10\n", encoding="utf-8")
    no_providers = GuiRunRequest(source, tmp_path / "out.csv", ())
    with pytest.raises(ValueError, match="Select at least one"):
        validate_run_request(no_providers)


def test_run_resolution_supports_provider_subset_and_writes_combined_csv(tmp_path: Path) -> None:
    """Use only selected providers while preserving overlaps and invalid diagnostics."""

    source = tmp_path / "input.csv"
    output = tmp_path / "combined.csv"
    source.write_text(
        "IPAddress\n"
        "198.51.100.10\n"
        "203.0.113.5\n"
        "0\n",
        encoding="utf-8",
    )

    ticks = iter((100.0, 101.25))
    result = run_resolution(
        GuiRunRequest(source, output, ("GCP", "AWS")),
        provider_builders=_builders(),
        clock=lambda: next(ticks),
    )

    assert result.request.providers == ("AWS", "GCP")
    assert result.elapsed_seconds == pytest.approx(1.25)
    assert len(result.input_batch.values) == 2
    assert len(result.input_batch.invalid) == 1
    assert result.workflow_result.matched_input_count == 2
    assert result.workflow_result.match_count_for("AWS") == 2
    assert result.workflow_result.match_count_for("GCP") == 1
    assert result.rows_written == 3

    with output.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["Provider"] for row in rows] == ["AWS", "AWS", "GCP"]
    assert rows[0]["AWS_NetworkBorderGroup"] == "eu-west-2"
    assert rows[-1]["GCP_Scope"] == "europe-west2"
    assert all(row["Azure_ServiceTagName"] == "" for row in rows)


def test_format_run_summary_explains_provider_and_overall_counts(tmp_path: Path) -> None:
    """Present key analyst-facing counts in clearly separated sections."""

    source = tmp_path / "input.csv"
    output = tmp_path / "combined.csv"
    source.write_text(
        "IPAddress\n198.51.100.10\n203.0.113.5\n0\n",
        encoding="utf-8",
    )
    ticks = iter((10.0, 10.5))
    result = run_resolution(
        GuiRunRequest(source, output, ("AWS", "GCP")),
        provider_builders=_builders(),
        clock=lambda: next(ticks),
    )

    summary = format_run_summary(result)

    assert "INPUT SUMMARY" in summary
    assert "PROVIDER RANGES" in summary
    assert "PROVIDER MATCHES" in summary
    assert "OVERALL RESULTS" in summary
    assert summary.count(SUMMARY_SEPARATOR) == 4
    assert "Valid input rows: 2" in summary
    assert "Invalid/skipped rows: 1" in summary
    assert "AWS: 2 prefixes (IPv4 2; IPv6 0)" in summary
    assert "AWS: 1 matched input rows; 2 output match rows" in summary
    assert "GCP: 1 matched input rows; 1 output match rows" in summary
    assert "Matched input rows: 2" in summary
    assert "Output match rows: 3" in summary
    assert "Completed in 0.50 seconds" in summary


def test_completion_status_is_short_and_explicit(tmp_path: Path) -> None:
    """Show an immediate success signal beside the GUI action buttons."""

    source = tmp_path / "input.csv"
    output = tmp_path / "combined.csv"
    source.write_text("IPAddress\n198.51.100.10\n", encoding="utf-8")
    ticks = iter((5.0, 6.75))
    result = run_resolution(
        GuiRunRequest(source, output, ("AWS",)),
        provider_builders=_builders(),
        clock=lambda: next(ticks),
    )

    assert format_completion_status(result) == "Completed successfully in 1.75 seconds"


class _FakeTextWidget:
    """Minimal text-widget stand-in for viewport behaviour tests."""

    def __init__(self) -> None:
        self.seen = None
        self.value = ""

    def configure(self, **_kwargs) -> None:
        """Accept state changes made by the production helper."""

    def delete(self, *_args) -> None:
        """Clear the fake text contents."""

        self.value = ""

    def insert(self, _index, text) -> None:
        """Record inserted text."""

        self.value = text

    def see(self, index) -> None:
        """Record which part of the text widget should become visible."""

        self.seen = index


def test_status_box_can_auto_scroll_to_overall_totals() -> None:
    """Successful runs should reveal the bottom summary rather than the first line."""

    app = CloudIpResolverApp.__new__(CloudIpResolverApp)
    app.status_text = _FakeTextWidget()

    app._set_status("line one\nline two", scroll_to_end=True)

    assert app.status_text.value == "line one\nline two"
    assert app.status_text.seen == "end"


class _FakeProgressbar:
    """Minimal progress-bar stand-in for the idle reset behaviour."""

    def __init__(self) -> None:
        self.stopped = False
        self.removed = False
        self.value = None

    def stop(self) -> None:
        """Record animation stop."""

        self.stopped = True

    def configure(self, **kwargs) -> None:
        """Capture the reset value supplied by the GUI."""

        self.value = kwargs.get("value")

    def grid_remove(self) -> None:
        """Record that the progress bar was hidden."""

        self.removed = True


def test_progress_bar_is_reset_and_hidden_after_run() -> None:
    """Completed/error runs should not leave a partial green progress indicator."""

    app = CloudIpResolverApp.__new__(CloudIpResolverApp)
    app.progress = _FakeProgressbar()

    app._hide_progress()

    assert app.progress.stopped
    assert app.progress.value == 0
    assert app.progress.removed
