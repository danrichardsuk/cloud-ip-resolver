"""Command-line interface for Cloud IP Resolver.

The CLI is intentionally an orchestration layer rather than the home of the
matching logic.  It converts command-line arguments into provider/workflow
objects, prints useful progress information, and delegates parsing, matching and
CSV writing to reusable modules.  This separation is important because the
future desktop GUI should call the same underlying code instead of reimplementing
it.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from .compare import compare_aws_csv, compare_azure_csv, compare_gcp_csv
from .io import (
    read_ip_csv,
    write_aws_matches_csv,
    write_azure_matches_csv,
    write_combined_matches_csv,
    write_gcp_matches_csv,
)
from .providers.aws import AwsProvider
from .providers.azure import AzureProvider
from .providers.gcp import GcpProvider
from .resolver import Resolver
from .workflow import MultiProviderResult, MultiProviderWorkflow


def build_parser() -> argparse.ArgumentParser:
    """Create the complete command-line grammar.

    Returns:
        Configured ``ArgumentParser`` containing provider resolution commands,
        the unified ``all`` command, and legacy parity-comparison commands.

    Keeping parser construction in its own function makes the CLI easy to test
    without launching a subprocess.
    """

    parser = argparse.ArgumentParser(
        prog="cloud-ip-resolver",
        description="Resolve public IP addresses against published cloud-provider ranges.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    aws = subparsers.add_parser("aws", help="Resolve a CSV against AWS public ranges")
    _add_resolve_arguments(aws, default_output="output_aws.csv")

    azure = subparsers.add_parser(
        "azure", help="Resolve a CSV against Azure Public Service Tags"
    )
    _add_resolve_arguments(azure, default_output="output_azure.csv")

    gcp = subparsers.add_parser(
        "gcp", help="Resolve a CSV against Google Cloud public ranges"
    )
    _add_resolve_arguments(gcp, default_output="output_gcp.csv")

    all_providers = subparsers.add_parser(
        "all", help="Resolve one CSV against AWS, Azure, and Google Cloud"
    )
    _add_all_resolve_arguments(all_providers)

    compare_aws = subparsers.add_parser(
        "compare-aws", help="Compare legacy and Python AWS output CSVs ignoring row order"
    )
    _add_compare_arguments(compare_aws)

    compare_azure = subparsers.add_parser(
        "compare-azure",
        help="Compare legacy and Python Azure output CSVs ignoring row order",
    )
    _add_compare_arguments(compare_azure)

    compare_gcp = subparsers.add_parser(
        "compare-gcp",
        help="Compare legacy and Python GCP output CSVs ignoring row order",
    )
    _add_compare_arguments(compare_gcp)
    return parser


def _add_resolve_arguments(parser: argparse.ArgumentParser, *, default_output: str) -> None:
    """Add arguments shared by one-provider resolution commands.

    Args:
        parser: Sub-parser to extend.
        default_output: Provider-specific filename used when ``-o`` is omitted.
    """

    parser.add_argument("input", type=Path, help="Input CSV containing an IPAddress column")
    parser.add_argument("-o", "--output", type=Path, default=Path(default_output))
    parser.add_argument(
        "--ranges-file",
        type=Path,
        help="Use a saved provider JSON file instead of downloading the current feed",
    )
    parser.add_argument("--ip-column", default="IPAddress")


def _add_all_resolve_arguments(parser: argparse.ArgumentParser) -> None:
    """Add arguments specific to the unified all-provider command.

    Each provider gets its own optional snapshot argument because AWS, Azure and
    GCP publish different files.  A caller can therefore pin any or all sources
    for a reproducible test while leaving the others live if desired.
    """

    parser.add_argument("input", type=Path, help="Input CSV containing an IPAddress column")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output_all.csv"),
        help="Combined output CSV path (default: output_all.csv)",
    )
    parser.add_argument("--ip-column", default="IPAddress")
    parser.add_argument(
        "--aws-ranges-file",
        type=Path,
        help="Use a saved AWS ip-ranges.json instead of the current feed",
    )
    parser.add_argument(
        "--azure-ranges-file",
        type=Path,
        help="Use a saved Azure ServiceTags_Public.json instead of the current feed",
    )
    parser.add_argument(
        "--gcp-ranges-file",
        type=Path,
        help="Use a saved Google Cloud cloud.json instead of the current feed",
    )


def _add_compare_arguments(parser: argparse.ArgumentParser) -> None:
    """Add common old/new CSV arguments to a parity-comparison command."""

    parser.add_argument("old", type=Path, help="Legacy PowerShell output CSV")
    parser.add_argument("new", type=Path, help="Python output CSV")
    parser.add_argument("--show", type=int, default=10)


def main(argv: list[str] | None = None) -> int:
    """Parse a command and dispatch it to the correct workflow.

    Args:
        argv: Optional argument list. ``None`` means use the real process command
            line; tests pass an explicit list to exercise the CLI in-process.

    Returns:
        Process-style exit code: ``0`` success, ``1`` parity difference, ``2``
        invalid input/configuration or I/O failure.
    """

    args = build_parser().parse_args(argv)
    try:
        if args.command == "aws":
            return _run_aws(args)
        if args.command == "azure":
            return _run_azure(args)
        if args.command == "gcp":
            return _run_gcp(args)
        if args.command == "all":
            return _run_all(args)
        if args.command == "compare-aws":
            return _run_compare(args, compare_aws_csv, label="AWS")
        if args.command == "compare-azure":
            return _run_compare(args, compare_azure_csv, label="Azure")
        if args.command == "compare-gcp":
            return _run_compare(args, compare_gcp_csv, label="GCP")
    except (OSError, ValueError) as exc:
        # Present expected user/data errors cleanly instead of a Python traceback.
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


def _read_batch(args: argparse.Namespace):
    """Read an input CSV and print concise validation diagnostics.

    Args:
        args: Parsed command arguments containing ``input`` and ``ip_column``.

    Returns:
        ``InputBatch`` from :func:`read_ip_csv`.

    Only the first five invalid rows are printed so a badly formed large file
    does not flood the terminal; the total invalid count is still reported.
    """

    print(f"Reading input: {args.input}")
    batch = read_ip_csv(args.input, column=args.ip_column)
    print(f"Valid IP rows: {len(batch.values):,}")
    if batch.invalid:
        print(f"Invalid/skipped rows: {len(batch.invalid):,}")
        for invalid in batch.invalid[:5]:
            display = invalid.value or "<empty>"
            print(f"  row {invalid.row_number}: {display} ({invalid.reason})")
        if len(batch.invalid) > 5:
            print(f"  ...and {len(batch.invalid) - 5:,} more")
    return batch


def _run_aws(args: argparse.Namespace) -> int:
    """Execute the AWS-only resolution path and write legacy-compatible CSV."""

    started = time.perf_counter()
    batch = _read_batch(args)
    provider = AwsProvider(ranges_file=args.ranges_file)
    source = str(args.ranges_file) if args.ranges_file else "current AWS feed"
    print(f"Loading AWS ranges: {source}")
    feed = provider.load_feed()
    print(
        f"AWS publication: {feed.create_date or 'unknown'}; "
        f"IPv4 prefixes: {feed.ipv4_count:,}; IPv6 prefixes: {feed.ipv6_count:,}"
    )
    return _resolve_and_write(
        started, batch, feed.prefixes, args.output, write_aws_matches_csv
    )


def _run_azure(args: argparse.Namespace) -> int:
    """Execute the Azure-only resolution path and write legacy-compatible CSV."""

    started = time.perf_counter()
    batch = _read_batch(args)
    provider = AzureProvider(ranges_file=args.ranges_file)
    source = (
        str(args.ranges_file)
        if args.ranges_file
        else "current Azure Service Tags feed"
    )
    print(f"Loading Azure ranges: {source}")
    feed = provider.load_feed()
    print(
        f"Azure cloud: {feed.cloud or 'unknown'}; change number: "
        f"{feed.change_number if feed.change_number is not None else 'unknown'}; "
        f"IPv4 prefixes: {feed.ipv4_count:,}; IPv6 prefixes: {feed.ipv6_count:,}"
    )
    return _resolve_and_write(
        started, batch, feed.prefixes, args.output, write_azure_matches_csv
    )


def _run_gcp(args: argparse.Namespace) -> int:
    """Execute the GCP-only resolution path and write legacy-compatible CSV."""

    started = time.perf_counter()
    batch = _read_batch(args)
    provider = GcpProvider(ranges_file=args.ranges_file)
    source = str(args.ranges_file) if args.ranges_file else "current Google Cloud feed"
    print(f"Loading Google Cloud ranges: {source}")
    feed = provider.load_feed()
    print(
        f"GCP publication: {feed.creation_time or 'unknown'}; "
        f"sync token: {feed.sync_token or 'unknown'}; "
        f"IPv4 prefixes: {feed.ipv4_count:,}; IPv6 prefixes: {feed.ipv6_count:,}"
    )
    return _resolve_and_write(
        started, batch, feed.prefixes, args.output, write_gcp_matches_csv
    )


def _run_all(args: argparse.Namespace) -> int:
    """Resolve one input list against AWS, Azure and GCP in a single workflow.

    Args:
        args: Parsed ``all`` command options, including optional per-provider
            snapshot files.

    Returns:
        ``0`` after writing the combined CSV successfully.
    """

    started = time.perf_counter()
    batch = _read_batch(args)

    workflow = MultiProviderWorkflow(
        [
            AwsProvider(ranges_file=args.aws_ranges_file),
            AzureProvider(ranges_file=args.azure_ranges_file),
            GcpProvider(ranges_file=args.gcp_ranges_file),
        ]
    )
    print("Loading AWS, Azure, and Google Cloud ranges...")
    result = workflow.resolve_many(batch.values)

    for summary in result.provider_summaries:
        print(
            f"{summary.provider}: {summary.prefix_count:,} prefixes "
            f"(IPv4: {summary.ipv4_count:,}; IPv6: {summary.ipv6_count:,})"
        )

    _print_provider_match_summary(result)

    rows = write_combined_matches_csv(args.output, result.resolutions)
    elapsed = time.perf_counter() - started
    print(f"Matched input rows: {result.matched_input_count:,}")
    print(f"Output match rows: {rows:,}")
    print(f"Output: {args.output}")
    print(f"Completed in {elapsed:.2f} seconds")
    return 0


def _print_provider_match_summary(result: MultiProviderResult) -> None:
    """Print per-provider input and output match counts for a combined run.

    Args:
        result: Completed multi-provider result.

    The two numbers are intentionally shown side by side. ``matched input rows``
    counts an input row once for that provider, whereas ``output match rows``
    includes every overlapping provider prefix that will appear in the CSV.
    """

    print("Provider matches:")
    for summary in result.provider_summaries:
        provider = summary.provider
        print(
            f"  {provider}: matched input rows "
            f"{result.matched_input_count_for(provider):,}; "
            f"output match rows {result.match_count_for(provider):,}"
        )


def _resolve_and_write(started, batch, prefixes, output, writer) -> int:
    """Shared execution path used by each single-provider command.

    Args:
        started: ``perf_counter`` value captured before input/provider loading.
        batch: Validated ``InputBatch``.
        prefixes: Provider prefix collection.
        output: Destination CSV path.
        writer: Provider-specific CSV writer function.

    Returns:
        ``0`` on success.
    """

    resolver = Resolver(prefixes)
    resolutions = resolver.resolve_many(batch.values)
    matched_inputs = sum(resolution.matched for resolution in resolutions)
    rows = writer(output, resolutions)
    elapsed = time.perf_counter() - started
    print(f"Matched input rows: {matched_inputs:,}")
    print(f"Output match rows: {rows:,}")
    print(f"Output: {output}")
    print(f"Completed in {elapsed:.2f} seconds")
    return 0


def _run_compare(args, comparer, *, label: str) -> int:
    """Run one provider's legacy-vs-Python parity comparison.

    Args:
        args: Parsed old/new CSV paths and display limit.
        comparer: Provider-specific comparison function.
        label: Human-readable provider name for terminal output.

    Returns:
        ``0`` for exact parity or ``1`` when differences exist.
    """

    only_old, only_new = comparer(args.old, args.new)
    if not only_old and not only_new:
        print(
            f"MATCH: both CSVs contain the same {label} match rows "
            "(row order ignored)."
        )
        return 0
    print(f"DIFFERENCE: {label} outputs are not identical.")
    print(f"Rows only in legacy output: {sum(only_old.values()):,}")
    _print_counter(only_old, args.show)
    print(f"Rows only in Python output: {sum(only_new.values()):,}")
    _print_counter(only_new, args.show)
    return 1


def _print_counter(rows, limit: int) -> None:
    """Print up to ``limit`` example rows from a difference counter.

    The leading ``xN`` shows duplicate multiplicity, which is useful when the
    same row appeared several times in only one of the compared files.
    """

    for shown, (row, count) in enumerate(rows.items()):
        if shown >= limit:
            break
        print(f"  x{count} | " + " | ".join(row))


if __name__ == "__main__":
    raise SystemExit(main())
