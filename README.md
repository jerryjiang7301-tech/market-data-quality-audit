# Market Data Quality Audit

A small, dependency-free Python tool for checking market-data files before a backtest.

**Background:** In a separate QQQ research project, I audited 3,128 hourly data files and found zero-row files and symbols with insufficient historical data. This project illustrates the checks; it does not reproduce that audit's complete results.

**Demo data:** Every file in `demo_data/` is fictional and created solely for this demonstration. No trading strategy, proprietary data, account information, or API credentials are included.

## Try it

Requires Python 3.9 or later. From the project directory:

```bash
python3 audit_market_data.py demo_data
```

The demo contains three fictional symbols: one passes, one has a short history, and one file is empty. The default minimum is five valid rows. The output lists problems per file and a summary.

```text
Symbol       Status  Finding
EMPTY        ERROR   empty file
HEALTHY      PASS    6 valid rows; 2026-01-05T09:30:00+00:00 to 2026-01-05T14:30:00+00:00
SHORT        WARN    short history: 2 valid rows (minimum: 5); 2026-01-05T09:30:00+00:00 to 2026-01-05T10:30:00+00:00

Summary: 3 files | 1 passed | 1 warning | 1 error
```

To use your own directory of CSV files, set the minimum history explicitly:

```bash
python3 audit_market_data.py /path/to/csv-files --min-rows 500 --strict
```

`--strict` returns exit code 1 when any warning or error is found, useful for automated pipelines. Without `--strict`, the command returns 0 after reporting findings. Invalid arguments or an unreadable directory return 2.

To create a per-symbol CSV report for review, add `--csv-report /path/to/report.csv`. The output must not already exist; the tool will not overwrite it. Put the report outside the input directory so it is not treated as market data in a later run.

## What it checks

Each CSV filename represents a symbol. Each nonempty CSV must have `timestamp,open,high,low,close,volume` columns. Timestamps must be ISO 8601 values consistently using a timezone or consistently without one within each file; aware timestamps are normalized to UTC. The tool checks empty or header-only files, missing columns, invalid timestamps, duplicate or out-of-order timestamps, invalid/non-finite numbers, nonpositive prices, negative volume, and OHLC consistency. For a clean file, it reports the first and last observations. A file with fewer valid rows than `--min-rows` receives a warning; row counts and date ranges are not a guarantee of continuous historical coverage.

It does **not** verify exchange calendars, missing bars, corporate actions, survivorship bias, timezones against an exchange, data vendor accuracy, or duplicate symbols. Passing these checks does not establish that a dataset is suitable for a backtest.

## Why it matters

Empty files and short histories can silently change the available investment universe or produce incomplete indicators. Invalid or duplicate bars can distort returns and introduce misleading results. Catching these issues before simulation makes exclusions visible and easier to review; it does not, on its own, prevent look-ahead bias or prove a strategy's performance.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

The checks and example data are intentionally small and designed to run locally without network access or extra packages.
