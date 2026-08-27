"""Launchable desktop presentation for Cloud IP Resolver.

The larger ``gui`` module owns reusable execution helpers and the base Tkinter
window. This module adds the final analyst-facing presentation: clearer match
terminology and a slightly taller results area. Keeping presentation wording
here means the resolver and CSV behaviour remain unchanged.
"""

from __future__ import annotations

from typing import Any

from .gui import (
    SUMMARY_SEPARATOR,
    CloudIpResolverApp as BaseCloudIpResolverApp,
    GuiRunResult,
    format_completion_status,
    tk,
)


def format_run_summary(result: GuiRunResult) -> str:
    """Build a results summary that explains what the match counts represent.

    ``Matched IP rows`` deliberately says *rows* rather than unique IPs because
    duplicate input rows are preserved by the resolver. ``CIDR matches`` is the
    number of individual IP-to-prefix matches written to the combined CSV, so a
    single IP row can contribute more than one CIDR match.
    """

    lines = [
        "INPUT SUMMARY",
        SUMMARY_SEPARATOR,
        f"Valid input rows: {len(result.input_batch.values):,}",
        f"Invalid/skipped rows: {len(result.input_batch.invalid):,}",
    ]

    if result.input_batch.invalid:
        lines.append("Invalid examples:")
        for invalid in result.input_batch.invalid[:5]:
            display = invalid.value or "<empty>"
            lines.append(f"  Row {invalid.row_number}: {display} ({invalid.reason})")
        if len(result.input_batch.invalid) > 5:
            lines.append(f"  ...and {len(result.input_batch.invalid) - 5:,} more")

    lines.extend(
        [
            "",
            "ABOUT THESE RESULTS",
            SUMMARY_SEPARATOR,
            "Matched IP rows = input rows with at least one published cloud CIDR match.",
            "CIDR matches = individual IP-to-prefix matches written to the output CSV.",
            "One IP row can match multiple CIDRs/providers, so provider counts can overlap.",
        ]
    )

    lines.extend(["", "PROVIDER RANGES", SUMMARY_SEPARATOR])
    for summary in result.workflow_result.provider_summaries:
        lines.append(
            f"  {summary.provider}: {summary.prefix_count:,} prefixes "
            f"(IPv4 {summary.ipv4_count:,}; IPv6 {summary.ipv6_count:,})"
        )

    lines.extend(["", "PROVIDER MATCHES", SUMMARY_SEPARATOR])
    for summary in result.workflow_result.provider_summaries:
        provider = summary.provider
        lines.append(
            f"  {provider}: "
            f"{result.workflow_result.matched_input_count_for(provider):,} matched IP rows; "
            f"{result.workflow_result.match_count_for(provider):,} CIDR matches"
        )

    lines.extend(
        [
            "",
            "OVERALL RESULTS",
            SUMMARY_SEPARATOR,
            f"Matched IP rows: {result.workflow_result.matched_input_count:,}",
            f"CIDR matches: {result.rows_written:,}",
            f"Completed in {result.elapsed_seconds:.2f} seconds",
            f"Output: {result.request.output_path}",
        ]
    )
    return "\n".join(lines)


class CloudIpResolverApp(BaseCloudIpResolverApp):
    """Polished desktop window using the analyst-facing result terminology."""

    def __init__(self, root: Any) -> None:
        """Create the base GUI, then give the Results area additional height."""

        super().__init__(root)
        # The width remains compact while the extra height accommodates the new
        # explanatory block without making the window feel unnecessarily wide.
        self.root.geometry("760x780")
        self.root.minsize(720, 700)
        self.status_text.configure(height=28)

    def _finish_success(self, result: GuiRunResult) -> None:
        """Display the contextualised results after a successful worker run."""

        self._stop_running_status()
        self._hide_progress()
        self.resolve_button.configure(state="normal")
        self._last_output = result.request.output_path
        self.open_folder_button.configure(state="normal")
        self.run_status_var.set(format_completion_status(result))
        # The taller result area is intended to show the complete summary, so
        # leave the viewport at the top rather than auto-scrolling.
        self._set_status(format_run_summary(result))


def main() -> int:
    """Launch the polished desktop application and block until it is closed."""

    if tk is None:
        raise RuntimeError(
            "Tkinter is not available in this Python installation. "
            "Install Python with Tcl/Tk support to run the desktop GUI."
        )

    root = tk.Tk()
    CloudIpResolverApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
