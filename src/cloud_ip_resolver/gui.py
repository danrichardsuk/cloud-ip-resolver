"""Tkinter desktop interface for Cloud IP Resolver.

The GUI deliberately stays thin: it collects file/provider choices, calls the
same reusable ``MultiProviderWorkflow`` used by the CLI, writes the combined
CSV, and presents the result counts in a form that an analyst can read quickly.
No cloud matching logic lives in the window code.

The potentially slow work (downloading provider feeds and resolving a large CSV)
runs on a background thread.  Tkinter itself is only touched from the main UI
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

# Importing this module should remain possible on headless test/build machines
# where the optional system Tk libraries may not be installed.  The actual GUI
# entry point gives a clear error if Tkinter is unavailable.
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


@dataclass(frozen=True, slots=True)
class GuiRunRequest:
    """Describe one resolution job requested by the desktop UI.

    Attributes:
        input_path: CSV containing the input IP-address column.
        output_path: Combined CSV destination.
        providers: Provider names to include, normally some subset of
            ``AWS``, ``Azure`` and ``GCP``.
        ip_column: Input column containing addresses.  ``IPAddress`` keeps the
            GUI compatible with the existing analyst files and CLI.
    """

    input_path: Path
    output_path: Path
    providers: tuple[str, ...]
    ip_column: str = "IPAddress"


@dataclass(frozen=True, slots=True)
class GuiRunResult:
    """Bundle everything the GUI needs to display after a completed job.

    Keeping this as data rather than updating widgets inside the resolver makes
    the execution path reusable and easy to unit-test without a graphical
    display.
    """

    request: GuiRunRequest
    input_batch: InputBatch
    workflow_result: MultiProviderResult
    rows_written: int
    elapsed_seconds: float


def normalise_provider_names(provider_names: Sequence[str]) -> tuple[str, ...]:
    """Validate provider names and return them in the standard display order.

    Args:
        provider_names: Names selected by the user.

    Returns:
        Unique provider names ordered AWS, Azure, GCP.

    Raises:
        ValueError: If no providers are selected or an unknown name is supplied.

    Normalising the order keeps terminal, CSV and GUI summaries predictable even
    if a caller constructs a request programmatically in a different order.
    """

    selected = tuple(provider_names)
    if not selected:
        raise ValueError("Select at least one cloud provider.")

    unknown = sorted(set(selected) - set(PROVIDER_ORDER))
    if unknown:
        raise ValueError("Unknown cloud provider(s): " + ", ".join(unknown))

    return tuple(name for name in PROVIDER_ORDER if name in set(selected))


def validate_run_request(request: GuiRunRequest) -> GuiRunRequest:
    """Validate paths/provider selection before starting network or matching work.

    Args:
        request: Candidate GUI request.

    Returns:
        A new request with provider names normalised into standard order.

    Raises:
        ValueError: For missing input/output values, a non-existent input file,
            an output path that points to a directory, or invalid provider names.
    """

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
    """Create provider adapters for the selected provider names.

    Args:
        provider_names: Valid provider names to instantiate.
        builders: Optional name-to-constructor mapping.  Production uses the live
            AWS/Azure/GCP adapters; tests inject tiny deterministic providers.

    Returns:
        Provider adapter instances in standard provider order.
    """

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

    Args:
        request: Input/output/provider choices from the GUI.
        provider_builders: Optional injected provider constructors for tests.
        clock: Timer function; injectable so elapsed-time formatting is testable.

    Returns:
        ``GuiRunResult`` containing input validation diagnostics, per-provider
        matches, output-row count and elapsed time.

    Raises:
        OSError: If input/provider/output I/O fails.
        ValueError: If the request or a provider feed is invalid.

    This is the key seam between UI and business logic.  A future Windows EXE
    still calls this same function; packaging does not change the resolver path.
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
    """Convert a completed run into the multi-line summary shown in the GUI.

    Args:
        result: Completed GUI resolution result.

    Returns:
        Human-readable text containing input validation, provider prefix counts,
        provider match counts, overall totals, elapsed time and output path.
    """

    lines = [
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

    lines.extend(["", "Provider ranges:"])
    for summary in result.workflow_result.provider_summaries:
        lines.append(
            f"  {summary.provider}: {summary.prefix_count:,} prefixes "
            f"(IPv4 {summary.ipv4_count:,}; IPv6 {summary.ipv6_count:,})"
        )

    lines.extend(["", "Provider matches:"])
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
            f"Matched input rows: {result.workflow_result.matched_input_count:,}",
            f"Output match rows: {result.rows_written:,}",
            f"Completed in {result.elapsed_seconds:.2f} seconds",
            f"Output: {result.request.output_path}",
        ]
    )
    return "\n".join(lines)


def default_output_path(input_path: str | Path) -> Path:
    """Choose ``output_all.csv`` beside the selected input file.

    An output next to the source is a familiar default for analyst workflows,
    while the Save/Browse button still lets the user choose any destination.
    """

    path = Path(input_path)
    parent = path.parent if str(path.parent) else Path.cwd()
    return parent / "output_all.csv"


def open_output_folder(output_path: str | Path) -> None:
    """Open the folder containing a generated output file in the OS file browser.

    Args:
        output_path: Output CSV whose parent directory should be opened.

    Raises:
        ValueError: If the parent folder does not exist.
        OSError: If the operating system cannot launch its file browser.
    """

    folder = Path(output_path).expanduser().resolve().parent
    if not folder.is_dir():
        raise ValueError(f"Output folder does not exist: {folder}")

    if os.name == "nt":
        # ``startfile`` is Windows-only, so getattr avoids static/platform issues
        # when the source is imported or tested on Linux/macOS.
        getattr(os, "startfile")(str(folder))
    elif sys.platform == "darwin":  # pragma: no cover - platform-specific UI.
        subprocess.Popen(["open", str(folder)])
    else:  # pragma: no cover - platform-specific UI.
        subprocess.Popen(["xdg-open", str(folder)])


class CloudIpResolverApp:
    """Main Tkinter window for selecting inputs, providers and viewing results."""

    def __init__(self, root: Any) -> None:
        """Create widgets and initialise the window's state.

        Args:
            root: Tkinter root window.  Accepting it from the caller follows the
                normal Tkinter pattern and makes lifecycle ownership explicit.

        Raises:
            RuntimeError: If this Python installation does not provide Tkinter.
        """

        if tk is None or ttk is None:
            raise RuntimeError(
                "Tkinter is not available in this Python installation. "
                "Install Python with Tcl/Tk support to run the desktop GUI."
            )

        self.root = root
        self.root.title("Cloud IP Resolver")
        self.root.minsize(760, 560)

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str(Path.cwd() / "output_all.csv"))
        self.provider_vars = {
            "AWS": tk.BooleanVar(value=True),
            "Azure": tk.BooleanVar(value=True),
            "GCP": tk.BooleanVar(value=True),
        }
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

        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(0, 10))

        result_frame = ttk.LabelFrame(outer, text="Results", padding=8)
        result_frame.grid(row=6, column=0, columnspan=3, sticky="nsew")
        result_frame.rowconfigure(0, weight=1)
        result_frame.columnconfigure(0, weight=1)
        self.status_text = tk.Text(result_frame, height=16, wrap="word", state="disabled")
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
        """Validate the form and start the expensive work on a background thread."""

        try:
            request = self._make_request()
        except ValueError as exc:
            self._show_error(str(exc))
            return

        self.resolve_button.configure(state="disabled")
        self.open_folder_button.configure(state="disabled")
        self.progress.start(10)
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
        """Run a resolution away from Tk's UI thread and marshal the result back."""

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
        """Restore controls and display the summary after a successful worker run."""

        self.progress.stop()
        self.resolve_button.configure(state="normal")
        self._last_output = result.request.output_path
        self.open_folder_button.configure(state="normal")
        self._set_status(format_run_summary(result))

    def _finish_error(self, message: str) -> None:
        """Restore controls and present a friendly error after a failed worker run."""

        self.progress.stop()
        self.resolve_button.configure(state="normal")
        self._set_status(f"Resolution failed.\n\n{message}")
        self._show_error(message)

    def _set_status(self, text: str) -> None:
        """Replace the read-only Results text while preserving its disabled state."""

        self.status_text.configure(state="normal")
        self.status_text.delete("1.0", "end")
        self.status_text.insert("1.0", text)
        self.status_text.configure(state="disabled")

    def _show_error(self, message: str) -> None:
        """Show a modal error dialog when Tkinter's messagebox service is available."""

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
    """Launch the desktop application and block until the user closes the window.

    Returns:
        ``0`` after a normal GUI shutdown.

    Raises:
        RuntimeError: If Tkinter is unavailable in this Python installation.
    """

    if tk is None:
        raise RuntimeError(
            "Tkinter is not available in this Python installation. "
            "Install Python with Tcl/Tk support to run the desktop GUI."
        )

    root = tk.Tk()
    CloudIpResolverApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":  # Allows ``python -m cloud_ip_resolver.gui`` in development.
    raise SystemExit(main())
