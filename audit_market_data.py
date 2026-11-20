"""Audit simple OHLCV CSV files without network access or third-party packages."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import math
from pathlib import Path
import sys

REQUIRED = {"timestamp", "open", "high", "low", "close", "volume"}


def positive_integer(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def audit_file(path: Path, min_rows: int) -> tuple[str, str]:
    try:
        if path.stat().st_size == 0:
            return "ERROR", "empty file"
        with path.open(encoding="utf-8-sig", newline="") as stream:
            reader = csv.DictReader(stream, strict=True)
            missing = REQUIRED - set(reader.fieldnames or [])
            if missing:
                return "ERROR", "missing columns: " + ", ".join(sorted(missing))
            valid = 0
            total = 0
            errors = []
            seen = set()
            previous = None
            first = None
            aware = None
            for line, row in enumerate(reader, start=2):
                total += 1
                try:
                    if None in row:
                        raise ValueError("extra CSV fields")
                    raw_timestamp = row.get("timestamp") or ""
                    stamp = datetime.fromisoformat(raw_timestamp.replace("Z", "+00:00"))
                    row_aware = stamp.utcoffset() is not None
                    if aware is not None and aware != row_aware:
                        raise ValueError("mixed timezone-aware and naive timestamps")
                    aware = row_aware
                    if row_aware:
                        stamp = stamp.astimezone(timezone.utc)
                    prices = [float(row.get(key) or "") for key in ("open", "high", "low", "close", "volume")]
                    op, high, low, close, volume = prices
                    if not all(math.isfinite(value) for value in prices):
                        raise ValueError("non-finite number")
                    if min(op, high, low, close) <= 0 or volume < 0:
                        raise ValueError("nonpositive price or negative volume")
                    if low > min(op, close) or high < max(op, close) or low > high:
                        raise ValueError("inconsistent OHLC")
                    if stamp in seen:
                        raise ValueError("duplicate timestamp")
                    if previous is not None and stamp < previous:
                        raise ValueError("out-of-order timestamp")
                    seen.add(stamp)
                    if first is None:
                        first = stamp
                    previous = stamp
                    valid += 1
                except (TypeError, ValueError, OverflowError) as exc:
                    errors.append(f"row {line}: {exc}")
            if total == 0:
                return "ERROR", "header only; no data rows"
            if errors:
                suffix = f"; {len(errors) - 1} more" if len(errors) > 1 else ""
                return "ERROR", errors[0] + suffix
            coverage = f"{first.isoformat()} to {previous.isoformat()}"
            if valid < min_rows:
                return "WARN", f"short history: {valid} valid rows (minimum: {min_rows}); {coverage}"
            return "PASS", f"{valid} valid rows; {coverage}"
    except (OSError, UnicodeError, csv.Error) as exc:
        return "ERROR", f"cannot read file: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check OHLCV CSV files before backtesting.")
    parser.add_argument("directory", type=Path, help="directory containing CSV files")
    parser.add_argument("--min-rows", type=positive_integer, default=5)
    parser.add_argument("--strict", action="store_true", help="return 1 if any checks fail or warn")
    parser.add_argument("--csv-report", type=Path, help="write a new CSV report (never overwrites an existing file)")
    args = parser.parse_args(argv)
    if not args.directory.is_dir():
        print(f"Error: not a readable directory: {args.directory}", file=sys.stderr)
        return 2
    try:
        files = sorted(p for p in args.directory.iterdir() if p.is_file() and p.suffix.lower() == ".csv")
    except OSError as exc:
        print(f"Error: cannot read directory ({type(exc).__name__})", file=sys.stderr)
        return 2
    if not files:
        print("Error: no CSV files found", file=sys.stderr)
        return 2
    counts = {"PASS": 0, "WARN": 0, "ERROR": 0}
    results = []
    print(f"{'Symbol':<12} {'Status':<6}  Finding")
    for path in files:
        status, message = audit_file(path, args.min_rows)
        counts[status] += 1
        results.append((path.stem, path.name, status, message))
        print(f"{path.stem:<12} {status:<6}  {message}")
    print(f"\nSummary: {len(files)} files | {counts['PASS']} passed | {counts['WARN']} warning | {counts['ERROR']} error")
    if args.csv_report:
        try:
            with args.csv_report.open("x", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream)
                writer.writerow(["symbol", "source_file", "status", "finding"])
                writer.writerows(results)
        except OSError as exc:
            print(f"Error: cannot create report ({type(exc).__name__})", file=sys.stderr)
            return 2
        print(f"Report: {args.csv_report}")
    return 1 if args.strict and (counts["WARN"] or counts["ERROR"]) else 0


if __name__ == "__main__":
    raise SystemExit(main())
