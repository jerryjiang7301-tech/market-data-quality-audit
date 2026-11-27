# Market Data Quality Audit

**Catch missing symbols and incomplete hourly price data before a backtest begins.**

[![Tests](https://github.com/jerryjiang7301-tech/market-data-quality-audit/actions/workflows/tests.yml/badge.svg)](https://github.com/jerryjiang7301-tech/market-data-quality-audit/actions/workflows/tests.yml)

A backtest can run without an error even when a symbol is missing or its history is too short. The resulting universe and indicator warm-up may differ from what the researcher intended. This small Python tool checks those inputs and produces an actionable per-symbol report.

The project is inspired by a real audit of **3,128 hourly files** in independent market-data research. It is a standalone demonstration of a data-quality problem relevant to my QQQ/P1 research workflow, not the production P1 implementation or a reproduction of that historical audit. All included data and schedules are synthetic. No licensed market data, proprietary signals, account information or credentials are included.

## Run the demo

Requires Python 3.9+ and no third-party packages:

```bash
git clone https://github.com/jerryjiang7301-tech/market-data-quality-audit.git
cd market-data-quality-audit
python3 audit_market_data.py demo_data --symbols demo_config/symbols.csv --schedule demo_config/schedule.csv
```

```text
Symbol       Status  Finding
EMPTY        ERROR   empty file
HEALTHY      PASS    6 valid rows; 2026-01-05T09:30:00+00:00 to 2026-01-05T14:30:00+00:00
MISSING      ERROR   expected symbol file missing
SHORT        WARN    short history: 2 valid rows (minimum: 5); missing 1 expected bars; first 2026-01-05T11:30:00+00:00; 2026-01-05T09:30:00+00:00 to 2026-01-05T10:30:00+00:00

Summary: 4 symbols | 1 passed | 1 warning | 2 error
```

The example has three data files and four expected symbols. The threshold of five rows and the timestamps are deliberately small, synthetic demonstration inputs, not a market calendar or an appropriate model warm-up policy. The historical 3,128-file count is not a result of this demo, and no backtest or repair outcome is claimed.

## Apply to a research dataset

Each input CSV filename is a case-sensitive symbol and must contain `timestamp,open,high,low,close,volume`. Input files are read directly from the specified directory, not recursively. Timestamps must be ISO 8601, consistently timezone-aware or consistently naive within a file; aware timestamps are normalized to UTC.

Optional inputs make the intended universe and coverage explicit:

- `--symbols symbols.csv`: CSV with a `symbol` column. Expected symbols without a matching file are errors. Extra data files are also audited; they are not silently discarded.
- `--schedule schedule.csv`: CSV with `symbol,timestamp` columns, one expected bar per row. Timestamps must have a timezone offset. Missing bars and symbols without an expected schedule are warnings. If both manifests are supplied, every schedule symbol must appear in the symbols list.
- `--start` and `--end`: inclusive ISO 8601 timestamps with timezone offsets. A file that starts later or ends earlier receives a warning. This checks the endpoints only; it does not establish continuity.
- `--min-rows`: minimum number of valid rows, default 5. This is a row count, not a measure of trading days or continuous history.
- `--strict`: return exit code 1 if any symbol has warnings or errors. Configuration errors return 2. Without `--strict`, completed audits return 0 even when findings exist.
- `--csv-report`: write a new per-symbol report without overwriting an existing file.

For example:

```bash
python3 audit_market_data.py /path/to/csv-files \
  --symbols /path/to/symbols.csv \
  --schedule /path/to/schedule.csv \
  --start 2026-01-05T09:30:00Z --end 2026-01-05T14:30:00Z \
  --min-rows 500 --strict --csv-report /path/to/report.csv
```

Generate an expected schedule from the correct exchange calendar, vendor timestamp convention, and each symbol's actual trading period **before** running this audit. Different instruments can have different expected rows. This tool does not infer holidays, early closes, daylight-saving changes, listing dates or suspensions. A sample schedule is not a substitute for a validated calendar. Data must be timezone-aware when using `--schedule` or coverage endpoints.

## Checks and limitations

The audit checks empty and header-only files, missing columns, invalid or inconsistent timestamps, duplicate or out-of-order timestamps, non-finite values, nonpositive prices, negative volume and inconsistent OHLC values. It can also compare files against an explicitly supplied expected universe, date endpoints and per-symbol timestamps.

It does **not** validate that the provided universe or schedule is correct, infer market sessions, verify corporate actions, eliminate survivorship bias, check vendor accuracy or guarantee a dataset is suitable for a backtest. An expected bar may legitimately be absent for an illiquid or suspended security depending on the vendor. A `PASS` means only that configured checks passed. The tool reports issues; it does not repair data or automatically connect to a trading system.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

Tests cover valid, empty and short data; missing symbols and bars; timezone handling; invalid input; command-line exit codes; and report overwrite protection. GitHub Actions runs the suite on each push.
