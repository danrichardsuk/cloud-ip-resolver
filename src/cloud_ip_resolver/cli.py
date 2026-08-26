"""Command-line interface for Cloud IP Resolver."""

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
    write_gcp_matches_csv,
)
from .providers.aws import AwsProvider
from .providers.azure import AzureProvider
from .providers.gcp import GcpProvider
from .resolver import Resolver


def build_parser() -> argparse.ArgumentParser:
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
    parser.add_argument("input", type=Path, help="Input CSV containing an IPAddress column")
    parser.add_argument("-o", "--output", type=Path, default=Path(default_output))
    parser.add_argument(
        "--ranges-file",
        type=Path,
        help="Use a saved provider JSON file instead of downloading the current feed",
    )
    parser.add_argument("--ip-column", default="IPAddress")


def _add_compare_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("old", type=Path, help="Legacy PowerShell output CSV")
    parser.add_argument("new", type=Path, help="Python output CSV")
    parser.add_argument("--show", type=int, default=10)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "aws":
            return _run_aws(args)
        if args.command == "azure":
            return _run_azure(args)
        if args.command == "gcp":
            return _run_gcp(args)
        if args.command == "compare-aws":
            return _run_compare(args, compare_aws_csv, label="AWS")
        if args.command == "compare-azure":
            return _run_compare(args, compare_azure_csv, label="Azure")
        if args.command == "compare-gcp":
            return _run_compare(args, compare_gcp_csv, label="GCP")
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return 2


def _read_batch(args: argparse.Namespace):
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


def _resolve_and_write(started, batch, prefixes, output, writer) -> int:
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
    for shown, (row, count) in enumerate(rows.items()):
        if shown >= limit:
            break
        print(f"  x{count} | " + " | ".join(row))


if __name__ == "__main__":
    raise SystemExit(main())
