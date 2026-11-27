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


def utc_timestamp(value: str) -> datetime:
    stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if stamp.utcoffset() is None:
        raise ValueError("timestamp must include a timezone offset")
    return stamp.astimezone(timezone.utc)


def read_manifest(path: Path, columns: set[str]) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, strict=True)
        if not columns.issubset(reader.fieldnames or []):
            raise ValueError("missing columns: " + ", ".join(sorted(columns)))
        rows = list(reader)
        if not rows or any(None in row or not all((row.get(c) or "").strip() for c in columns) for row in rows):
            raise ValueError("manifest is empty or contains incomplete rows")
        return rows


def audit_file(path: Path, min_rows: int, *, start: datetime | None = None,
               end: datetime | None = None, expected: set[datetime] | None = None) -> tuple[str, str]:
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
            if (start is not None or expected is not None) and not aware:
                return "ERROR", "timezone-aware data required for coverage or schedule checks"
            warnings = []
            if valid < min_rows:
                warnings.append(f"short history: {valid} valid rows (minimum: {min_rows})")
            if start is not None and (first > start or previous < end):
                warnings.append("does not cover requested endpoints")
            if expected is not None:
                missing_times = sorted(expected - seen)
                if missing_times:
                    warnings.append(f"missing {len(missing_times)} expected bars; first {missing_times[0].isoformat()}")
            if warnings:
                return "WARN", "; ".join(warnings) + "; " + coverage
            return "PASS", f"{valid} valid rows; {coverage}"
    except (OSError, UnicodeError, csv.Error) as exc:
        return "ERROR", f"cannot read file: {type(exc).__name__}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check OHLCV CSV files before backtesting.")
    parser.add_argument("directory", type=Path, help="directory containing CSV files")
    parser.add_argument("--min-rows", type=positive_integer, default=5)
    parser.add_argument("--strict", action="store_true", help="return 1 if any checks fail or warn")
    parser.add_argument("--csv-report", type=Path, help="write a new CSV report (never overwrites an existing file)")
    parser.add_argument("--symbols", type=Path, help="CSV with expected symbol column")
    parser.add_argument("--schedule", type=Path, help="CSV with expected symbol,timestamp rows")
    parser.add_argument("--start", help="inclusive coverage start with timezone offset")
    parser.add_argument("--end", help="inclusive coverage end with timezone offset")
    args = parser.parse_args(argv)
    try:
        if bool(args.start) != bool(args.end):
            raise ValueError("--start and --end must be provided together")
        start, end = (utc_timestamp(args.start), utc_timestamp(args.end)) if args.start else (None, None)
        if start is not None and start > end:
            raise ValueError("--start must not be later than --end")
        symbols = None
        if args.symbols:
            names = [row["symbol"].strip() for row in read_manifest(args.symbols, {"symbol"})]
            if len(set(names)) != len(names):
                raise ValueError("duplicate expected symbol")
            symbols = set(names)
        schedule = None
        if args.schedule:
            schedule = {}
            for row in read_manifest(args.schedule, {"symbol", "timestamp"}):
                symbol, stamp = row["symbol"].strip(), utc_timestamp(row["timestamp"].strip())
                if symbols is not None and symbol not in symbols:
                    raise ValueError(f"schedule symbol not in expected symbols: {symbol}")
                times = schedule.setdefault(symbol, set())
                if stamp in times:
                    raise ValueError(f"duplicate expected timestamp for {symbol}")
                times.add(stamp)
    except (OSError, UnicodeError, csv.Error, ValueError) as exc:
        print(f"Error: invalid audit configuration: {exc}", file=sys.stderr)
        return 2
    if not args.directory.is_dir():
        print(f"Error: not a readable directory: {args.directory}", file=sys.stderr)
        return 2
    try:
        manifests = {p.resolve() for p in (args.symbols, args.schedule) if p is not None}
        files = sorted(p for p in args.directory.iterdir() if p.is_file() and p.suffix.lower() == ".csv" and p.resolve() not in manifests)
    except OSError as exc:
        print(f"Error: cannot read directory ({type(exc).__name__})", file=sys.stderr)
        return 2
    if not files and not symbols and not schedule:
        print("Error: no CSV files found", file=sys.stderr)
        return 2
    by_symbol = {}
    for path in files:
        if path.stem in by_symbol:
            print(f"Error: multiple CSV files for symbol {path.stem}", file=sys.stderr)
            return 2
        by_symbol[path.stem] = path
    universe = set(by_symbol) | (symbols or set()) | (set(schedule) if schedule is not None else set())
    counts = {"PASS": 0, "WARN": 0, "ERROR": 0}
    results = []
    print(f"{'Symbol':<12} {'Status':<6}  Finding")
    for symbol in sorted(universe):
        path = by_symbol.get(symbol)
        if path is None:
            status, message = "ERROR", "expected symbol file missing"
        else:
            expected = schedule.get(symbol) if schedule is not None else None
            status, message = audit_file(path, args.min_rows, start=start, end=end, expected=expected)
            if schedule is not None and expected is None and status != "ERROR":
                status, message = "WARN", "no expected schedule for symbol; " + message
        counts[status] += 1
        results.append((symbol, path.name if path else "", status, message))
        print(f"{symbol:<12} {status:<6}  {message}")
    print(f"\nSummary: {len(universe)} symbols | {counts['PASS']} passed | {counts['WARN']} warning | {counts['ERROR']} error")
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
