"""Tkinter desktop interface for Cloud IP Resolver.

The GUI deliberately stays thin: it collects file/provider choices, calls the
same reusable ``MultiProviderWorkflow`` used by the CLI, writes the combined
CSV, and presents the result counts in a form that an analyst can read quickly.
No cloud matching logic lives in the window code.

The potentially slow work (downloading provider feeds and resolving a large CSV)
runs on a background thread. Tkinter itself is only touched from the main UI
thread, which keeps the window responsive while a resolution is running.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from typing import Any

from .io import InputBatch, read_ip_csv, write_combined_matches_csv
from .providers.aws import AwsProvider
from .providers.azure import AzureProvider
from .providers.gcp import GcpProvider
from .workflow import MultiProviderResult, MultiProviderWorkflow

try:  # pragma: no cover - availability depends on the Python installation.
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover
    tk = None
    filedialog = None
    messagebox = None
    ttk = None


PROVIDER_ORDER = ("AWS", "Azure", "GCP")
DEFAULT_PROVIDER_BUILDERS: Mapping[str, Callable[[], Any]] = {
    "AWS": AwsProvider,
    "Azure": AzureProvider,
    "GCP": GcpProvider,
}

# A simple ASCII separator keeps the result summary readable in the Tk text box
# and remains safe if it is copied into email, tickets, or terminals.
SUMMARY_SEPARATOR = "-" * 44


@dataclass(frozen=True, slots=True)
class GuiRunRequest:
    """Describe one resolution job requested by the desktop UI.

    Attributes:
        input_path: CSV containing the input IP-address column.
        output_path: Combined CSV destination.
        providers: Provider names to include, normally some subset of
            ``AWS``, ``Azure`` and ``GCP``.
        ip_column: Input column containing addresses. ``IPAddress`` keeps the
            GUI compatible with the existing analyst files and CLI.
    """

    input_path: Path
    output_path: Path
    providers: tuple[str, ...]
    ip_column: str = "IPAddress"


@dataclass(frozen=True, slots=True)
class GuiRunResult:
    """Bundle everything the GUI needs to display after a completed job."""

    request: GuiRunRequest
    input_batch: InputBatch
    workflow_result: MultiProviderResult
    rows_written: int
    elapsed_seconds: float


def normalise_provider_names(provider_names: Sequence[str]) -> tuple[str, ...]:
    """Validate provider names and return them in the standard display order.

    Raises:
        ValueError: If no providers are selected or an unknown name is supplied.
    """

    selected = tuple(provider_names)
    if not selected:
        raise ValueError("Select at least one cloud provider.")

    unknown = sorted(set(selected) - set(PROVIDER_ORDER))
    if unknown:
        raise ValueError("Unknown cloud provider(s): " + ", ".join(unknown))

    return tuple(name for name in PROVIDER_ORDER if name in set(selected))


def validate_run_request(request: GuiRunRequest) -> GuiRunRequest:
    """Validate paths/provider selection before network or matching work begins."""

    input_path = Path(request.input_path)
    output_path = Path(request.output_path)

    if not str(input_path).strip():
        raise ValueError("Choose an input CSV file.")
    if not input_path.is_file():
        raise ValueError(f"Input CSV does not exist: {input_path}")
    if not str(output_path).strip():
        raise ValueError("Choose an output CSV file.")
    if output_path.exists() and output_path.is_dir():
        raise ValueError(f"Output path is a folder, not a CSV file: {output_path}")

    providers = normalise_provider_names(request.providers)
    return GuiRunRequest(
        input_path=input_path,
        output_path=output_path,
        providers=providers,
        ip_column=request.ip_column,
    )


def build_providers(
    provider_names: Sequence[str],
    *,
    builders: Mapping[str, Callable[[], Any]] | None = None,
) -> tuple[Any, ...]:
    """Create provider adapters for the selected provider names."""

    names = normalise_provider_names(provider_names)
    provider_builders = builders or DEFAULT_PROVIDER_BUILDERS

    missing = [name for name in names if name not in provider_builders]
    if missing:
        raise ValueError("No provider builder configured for: " + ", ".join(missing))

    return tuple(provider_builders[name]() for name in names)


def run_resolution(
    request: GuiRunRequest,
    *,
    provider_builders: Mapping[str, Callable[[], Any]] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> GuiRunResult:
    """Execute one GUI resolution job without interacting with Tkinter widgets.

    This is the seam between UI and business logic. The Windows executable will
    continue to call this same function, so packaging does not change resolver
    behaviour.
    """

    validated = validate_run_request(request)
    started = clock()

    batch = read_ip_csv(validated.input_path, column=validated.ip_column)
    providers = build_providers(validated.providers, builders=provider_builders)
    workflow_result = MultiProviderWorkflow(providers).resolve_many(batch.values)
    rows_written = write_combined_matches_csv(
        validated.output_path,
        workflow_result.resolutions,
    )

    elapsed = clock() - started
    return GuiRunResult(
        request=validated,
        input_batch=batch,
        workflow_result=workflow_result,
        rows_written=rows_written,
        elapsed_seconds=elapsed,
    )


def format_run_summary(result: GuiRunResult) -> str:
    """Convert a completed run into the structured summary shown in the GUI.

    Section headings and separators are included because a real three-provider
    run can contain enough lines that a flat block of text is difficult to scan.
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
            f"{result.workflow_result.matched_input_count_for(provider):,} matched input rows; "
            f"{result.workflow_result.match_count_for(provider):,} output match rows"
        )

    lines.extend(
        [
            "",
            "OVERALL RESULTS",
            SUMMARY_SEPARATOR,
            f"Matched input rows: {result.workflow_result.matched_input_count:,}",
            f"Output match rows: {result.rows_written:,}",
            f"Completed in {result.elapsed_seconds:.2f} seconds",
            f"Output: {result.request.output_path}",
        ]
    )
    return "\n".join(lines)


def format_completion_status(result: GuiRunResult) -> str:
    """Return the concise success message displayed beside the action buttons."""

    return f"Completed successfully in {result.elapsed_seconds:.2f} seconds"


def default_output_path(input_path: str | Path) -> Path:
    """Choose ``output_all.csv`` beside the selected input file."""

    path = Path(input_path)
    parent = path.parent if str(path.parent) else Path.cwd()
    return parent / "output_all.csv"


def open_output_folder(output_path: str | Path) -> None:
    """Open the folder containing a generated output file in the OS file browser."""

    folder = Path(output_path).expanduser().resolve().parent
    if not folder.is_dir():
        raise ValueError(f"Output folder does not exist: {folder}")

    if os.name == "nt":
        getattr(os, "startfile")(str(folder))
    elif sys.platform == "darwin":  # pragma: no cover - platform-specific UI.
        subprocess.Popen(["open", str(folder)])
    else:  # pragma: no cover - platform-specific UI.
        subprocess.Popen(["xdg-open", str(folder)])


class CloudIpResolverApp:
    """Main Tkinter window for selecting inputs, providers and viewing results."""

    def __init__(self, root: Any) -> None:
        """Create widgets and initialise the window's state."""

        if tk is None or ttk is None:
            raise RuntimeError(
                "Tkinter is not available in this Python installation. "
                "Install Python with Tcl/Tk support to run the desktop GUI."
            )

        self.root = root
        self.root.title("Cloud IP Resolver")
        # Slightly taller than GUI v1 so the final totals are visible more often
        # on a normal Windows display while the window remains freely resizable.
        self.root.geometry("820x680")
        self.root.minsize(800, 640)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output_all.csv"))
        self.provider_vars = {
            "AWS": tk.BooleanVar(value=True),
            "Azure": tk.BooleanVar(value=True),
            "GCP": tk.BooleanVar(value=True),
        }
        self.run_status_var = tk.StringVar(value="Ready")
        self._last_output: Path | None = None

        self._build_widgets()

    def _build_widgets(self) -> None:
        """Lay out the input, provider, output, action and result controls."""

        outer = ttk.Frame(self.root, padding=16)
        outer.grid(row=0, column=0, sticky="nsew")
        self.root.rowconfigure(0, weight=1)
        self.root.columnconfigure(0, weight=1)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(6, weight=1)

        title = ttk.Label(outer, text="Cloud IP Resolver", font=("Segoe UI", 16, "bold"))
        title.grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        ttk.Label(outer, text="Input CSV").grid(row=1, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(outer, textvariable=self.input_var).grid(row=1, column=1, sticky="ew")
        ttk.Button(outer, text="Browse...", command=self._browse_input).grid(
            row=1, column=2, padx=(8, 0)
        )

        provider_frame = ttk.LabelFrame(outer, text="Providers", padding=(10, 6))
        provider_frame.grid(row=2, column=0, columnspan=3, sticky="ew", pady=12)
        for column, provider in enumerate(PROVIDER_ORDER):
            label = "Google Cloud" if provider == "GCP" else provider
            ttk.Checkbutton(
                provider_frame,
                text=label,
                variable=self.provider_vars[provider],
            ).grid(row=0, column=column, sticky="w", padx=(0, 20))

        ttk.Label(outer, text="Output CSV").grid(row=3, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(outer, textvariable=self.output_var).grid(row=3, column=1, sticky="ew")
        ttk.Button(outer, text="Browse...", command=self._browse_output).grid(
            row=3, column=2, padx=(8, 0)
        )

        actions = ttk.Frame(outer)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=14)
        self.resolve_button = ttk.Button(actions, text="Resolve", command=self._start_resolution)
        self.resolve_button.pack(side="left")
        self.open_folder_button = ttk.Button(
            actions,
            text="Open Output Folder",
            command=self._open_output_folder,
            state="disabled",
        )
        self.open_folder_button.pack(side="left", padx=(8, 0))
        ttk.Label(actions, textvariable=self.run_status_var).pack(side="left", padx=(16, 0))

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        # It is useful only while work is active. Hiding it while idle prevents
        # the partly filled green block that otherwise remains after a run.
        self.progress.grid_remove()

        result_frame = ttk.LabelFrame(outer, text="Results", padding=10)
        result_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        self.status_text = tk.Text(
            result_frame,
            height=20,
            wrap="word",
            state="disabled",
            font=("Consolas", 10),
            padx=6,
            pady=6,
        )
        self.status_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(result_frame, orient="vertical", command=self.status_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.status_text.configure(yscrollcommand=scrollbar.set)
        self._set_status("Choose an input CSV, select providers, then click Resolve.")

    def _browse_input(self) -> None:
        """Ask the user for an input CSV and choose a sensible output beside it."""

        if filedialog is None:
            return
        selected = filedialog.askopenfilename(
            title="Choose input CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if selected:
            self.input_var.set(selected)
            self.output_var.set(str(default_output_path(selected)))

    def _browse_output(self) -> None:
        """Ask the user where the combined CSV should be written."""

        if filedialog is None:
            return
        current = Path(self.output_var.get() or "output_all.csv")
        selected = filedialog.asksaveasfilename(
            title="Choose output CSV",
            defaultextension=".csv",
            initialdir=str(current.parent),
            initialfile=current.name,
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
        )
        if selected:
            self.output_var.set(selected)

    def _selected_providers(self) -> tuple[str, ...]:
        """Return provider names whose checkboxes are currently selected."""

        return tuple(
            provider for provider in PROVIDER_ORDER if self.provider_vars[provider].get()
        )

    def _make_request(self) -> GuiRunRequest:
        """Translate the current widget values into a validated run request."""

        request = GuiRunRequest(
            input_path=Path(self.input_var.get().strip()),
            output_path=Path(self.output_var.get().strip()),
            providers=self._selected_providers(),
        )
        return validate_run_request(request)

    def _start_resolution(self) -> None:
        """Validate the form and start expensive work on a background thread."""

        try:
            request = self._make_request()
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.resolve_button.configure(state="disabled")
        self.open_folder_button.configure(state="disabled")
        self.run_status_var.set("Resolving...")
        self._show_progress()
        self._set_status(
            "Resolving IP addresses...\n\n"
            "Provider feeds are being loaded and the input file is being matched."
        )

        worker = threading.Thread(
            target=self._resolution_worker,
            args=(request,),
            daemon=True,
        )
        worker.start()

    def _resolution_worker(self, request: GuiRunRequest) -> None:
        """Run resolution away from Tk's UI thread and marshal the result back."""

        try:
            result = run_resolution(request)
        except (OSError, ValueError) as exc:
            message = str(exc)
            self.root.after(0, lambda message=message: self._finish_error(message))
            return
        except Exception as exc:  # Defensive UI boundary: never crash the window.
            message = f"Unexpected error: {exc}"
            self.root.after(0, lambda message=message: self._finish_error(message))
            return

        self.root.after(0, lambda result=result: self._finish_success(result))

    def _finish_success(self, result: GuiRunResult) -> None:
        """Restore controls and display the summary after a successful run."""

        self._hide_progress()
        self.resolve_button.configure(state="normal")
        self._last_output = result.request.output_path
        self.open_folder_button.configure(state="normal")
        self.run_status_var.set(format_completion_status(result))
        # Overall totals are at the bottom, so reveal them immediately.
        self._set_status(format_run_summary(result), scroll_to_end=True)

    def _finish_error(self, message: str) -> None:
        """Restore controls and present a friendly error after a failed run."""

        self._hide_progress()
        self.resolve_button.configure(state="normal")
        self.open_folder_button.configure(
            state="normal" if self._last_output is not None else "disabled"
        )
        self.run_status_var.set("Resolution failed")
        self._set_status(f"Resolution failed.\n\n{message}")
        self._show_error(message)

    def _show_progress(self) -> None:
        """Reveal and animate the indeterminate progress indicator."""

        self.progress.grid()
        self.progress.start(10)

    def _hide_progress(self) -> None:
        """Stop, reset, and hide the progress indicator after a run finishes."""

        self.progress.stop()
        self.progress.configure(value=0)
        self.progress.grid_remove()

    def _set_status(self, text: str, *, scroll_to_end: bool = False) -> None:
        """Replace Results text and position its viewport sensibly.

        Args:
            text: Complete replacement text.
            scroll_to_end: When true, reveal the bottom so overall totals and
                completion information are immediately visible.
        """

        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")
        self.status_text.see("end" if scroll_to_end else "1.0")

    def _show_error(self, message: str) -> None:
        """Show a modal error dialog when Tkinter's messagebox is available."""

        if messagebox is not None:
            messagebox.showerror("Cloud IP Resolver", message)

    def _open_output_folder(self) -> None:
        """Open the last successful output directory and report launch failures."""

        if self._last_output is None:
            self._show_error("No output has been created yet.")
            return
        try:
            open_output_folder(self._last_output)
        except (OSError, ValueError) as exc:
            self._show_error(str(exc))


def main() -> int:
    """Launch the desktop application and block until the user closes the window."""

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
