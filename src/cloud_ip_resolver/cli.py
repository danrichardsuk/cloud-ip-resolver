"""Command-line interface for Cloud IP Resolver."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import time

from .compare import compare_aws_csv
from .io import read_ip_csv, write_aws_matches_csv
from .providers.aws import AwsProvider
from .resolver import Resolver


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cloud-ip-resolver",
        description="Resolve public IP addresses against published cloud-provider ranges.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    aws = subparsers.add_parser("aws", help="Resolve a CSV against AWS public ranges")
    aws.add_argument("input", type=Path, help="Input CSV containing an IPAddress column")
    aws.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("output_aws.csv"),
        help="Output CSV path (default: output_aws.csv)",
    )
    aws.add_argument(
        "--ranges-file",
        type=Path,
        help="Use a saved AWS ip-ranges.json instead of downloading the current feed",
    )
    aws.add_argument(
        "--ip-column",
        default="IPAddress",
        help="Input CSV column containing addresses (default: IPAddress)",
    )

    compare = subparsers.add_parser(
        "compare-aws",
        help="Compare legacy and Python AWS output CSVs ignoring row order",
    )
    compare.add_argument("old", type=Path, help="Legacy PowerShell output CSV")
    compare.add_argument("new", type=Path, help="Python output CSV")
    compare.add_argument(
        "--show",
        type=int,
        default=10,
        help="Maximum differing rows to display from each side (default: 10)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "aws":
            return _run_aws(args)
        if args.command == "compare-aws":
            return _run_compare_aws(args)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

    return 2


def _run_aws(args: argparse.Namespace) -> int:
    started = time.perf_counter()

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

    provider = AwsProvider(ranges_file=args.ranges_file)
    source = str(args.ranges_file) if args.ranges_file else "current AWS feed"
    print(f"Loading AWS ranges: {source}")
    feed = provider.load_feed()
    print(
        "AWS publication: "
        f"{feed.create_date or 'unknown'}; "
        f"IPv4 prefixes: {feed.ipv4_count:,}; "
        f"IPv6 prefixes: {feed.ipv6_count:,}"
    )

    resolver = Resolver(feed.prefixes)
    resolutions = resolver.resolve_many(batch.values)
    matched_inputs = sum(resolution.matched for resolution in resolutions)
    rows = write_aws_matches_csv(args.output, resolutions)

    elapsed = time.perf_counter() - started
    print(f"Matched input rows: {matched_inputs:,}")
    print(f"Output match rows: {rows:,}")
    print(f"Output: {args.output}")
    print(f"Completed in {elapsed:.2f} seconds")
    return 0


def _run_compare_aws(args: argparse.Namespace) -> int:
    only_old, only_new = compare_aws_csv(args.old, args.new)

    if not only_old and not only_new:
        print("MATCH: both CSVs contain the same AWS match rows (row order ignored).")
        return 0

    print("DIFFERENCE: AWS outputs are not identical.")
    print(f"Rows only in legacy output: {sum(only_old.values()):,}")
    _print_counter(only_old, args.show)
    print(f"Rows only in Python output: {sum(only_new.values()):,}")
    _print_counter(only_new, args.show)
    return 1


def _print_counter(rows, limit: int) -> None:
    shown = 0
    for row, count in rows.items():
        if shown >= limit:
            break
        print(f"  x{count} | " + " | ".join(row))
        shown += 1


if __name__ == "__main__":
    raise SystemExit(main())
