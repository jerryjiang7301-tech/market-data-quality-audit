# Market Data Quality Audit

**A small Python tool for checking hourly market data before backtesting.**

[![Tests](https://github.com/jerryjiang7301-tech/market-data-quality-audit/actions/workflows/tests.yml/badge.svg)](https://github.com/jerryjiang7301-tech/market-data-quality-audit/actions/workflows/tests.yml)

During an independent market-data research project, I audited **3,128 hourly data files** and found empty files and symbols with insufficient history. This repository is a standalone demonstration inspired by that work. It does not reproduce the original audit or disclose any proprietary strategy.

**All data in this repository is synthetic.** No licensed market data, trading signals, account information or credentials are included.

## At A Glance

| Demonstration | Finding | Why it matters |
| --- | --- | --- |
| `HEALTHY` | Sufficient valid observations | Ready for further quality review |
| `EMPTY` | No data rows | A silently missing symbol can change the research universe |
| `SHORT` | Fewer observations than the chosen minimum | Insufficient history can leave indicators incomplete |

The number of files above describes the historical audit, not the three-file demo. This project makes no claim about backtest returns or the outcome of fixing the historical data.

## Run The Demo

Requires Python 3.9+ and no third-party packages:

```bash
git clone https://github.com/jerryjiang7301-tech/market-data-quality-audit.git
cd market-data-quality-audit
python3 audit_market_data.py demo_data
```

The output is a per-symbol report:

```text
Symbol       Status  Finding
EMPTY        ERROR   empty file
HEALTHY      PASS    6 valid rows; 2026-01-05T09:30:00+00:00 to 2026-01-05T14:30:00+00:00
SHORT        WARN    short history: 2 valid rows (minimum: 5); 2026-01-05T09:30:00+00:00 to 2026-01-05T10:30:00+00:00

Summary: 3 files | 1 passed | 1 warning | 1 error
```

## Use Your Own Data

Each CSV filename represents a symbol. Files must contain `timestamp,open,high,low,close,volume` columns. Timestamps must be ISO 8601, consistently timezone-aware or consistently naive within each file. Aware timestamps are normalized to UTC.

```bash
python3 audit_market_data.py /path/to/csv-files --min-rows 500 --strict
```

The minimum is a **row count**, not a guarantee of continuous historical coverage. `--strict` returns exit code 1 for warnings or errors; invalid arguments, an unreadable directory or no CSV files return 2. Without `--strict`, findings are reported and the command returns 0.

To create a per-symbol CSV report, add `--csv-report /path/to/report.csv`. The report must not already exist: the tool will not overwrite it. Place it outside the input directory to avoid treating it as market data in a later run.

## Checks And Limits

The audit checks empty and header-only files, missing columns, invalid or inconsistent timestamps, duplicate or out-of-order timestamps, non-finite values, nonpositive prices, negative volume and inconsistent OHLC values. For valid files it shows the first and last observations.

It does **not** validate exchange calendars or missing bars, corporate actions, survivorship bias, exchange-specific timezones, vendor accuracy or duplicate symbols. Passing the audit does not establish that a dataset is complete or suitable for a backtest.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Tests cover normal, empty and short files, invalid data, command-line exit codes and report overwrite protection. The demo and tests run locally without network access.
