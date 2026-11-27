import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_market_data import audit_file, utc_timestamp

ROOT = Path(__file__).resolve().parents[1]
HEADER = "timestamp,open,high,low,close,volume\n"


class AuditTests(unittest.TestCase):
    def test_demo(self):
        self.assertEqual(audit_file(ROOT / "demo_data/EMPTY.csv", 5)[0], "ERROR")
        self.assertEqual(audit_file(ROOT / "demo_data/SHORT.csv", 5)[0], "WARN")
        self.assertEqual(audit_file(ROOT / "demo_data/HEALTHY.csv", 5)[0], "PASS")

    def check(self, text, phrase):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.csv"
            path.write_text(text, encoding="utf-8")
            status, message = audit_file(path, 1)
            self.assertEqual(status, "ERROR")
            self.assertIn(phrase, message)

    def test_missing_and_header_only(self):
        self.check("timestamp,open\n", "missing columns")
        self.check(HEADER, "header only")

    def test_duplicate_and_bad_values(self):
        row = "2026-01-01T10:00:00Z,10,11,9,10,100\n"
        self.check(HEADER + row + row, "duplicate timestamp")
        self.check(HEADER + "2026-01-01,10,11,9,NaN,100\n", "non-finite")
        self.check(HEADER + "2026-01-01,10,9,8,10,100\n", "inconsistent OHLC")
        self.check(HEADER + "2026-01-01,10,11,9,10,-1\n", "negative volume")

    def test_timestamp_order_and_mixed_timezone(self):
        self.check(HEADER + "2026-01-02,10,11,9,10,100\n2026-01-01,10,11,9,10,100\n", "out-of-order")
        self.check(HEADER + "2026-01-01T00:00:00Z,10,11,9,10,100\n2026-01-02,10,11,9,10,100\n", "mixed timezone")

    def test_cli_exit_codes(self):
        cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(ROOT / "demo_data")]
        self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
        self.assertEqual(subprocess.run(cmd + ["--strict"], capture_output=True).returncode, 1)
        self.assertEqual(subprocess.run(cmd + ["--min-rows", "0"], capture_output=True).returncode, 2)
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(subprocess.run([sys.executable, str(ROOT / "audit_market_data.py"), directory], capture_output=True).returncode, 2)

    def test_report_and_overwrite_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            report = Path(directory) / "report.csv"
            cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(ROOT / "demo_data"), "--csv-report", str(report)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 0)
            original = report.read_text(encoding="utf-8")
            self.assertIn("symbol,source_file,status,finding", original)
            self.assertIn("HEALTHY,HEALTHY.csv,PASS", original)
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            self.assertEqual(report.read_text(encoding="utf-8"), original)

    def test_expected_bars_and_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ABC.csv"
            path.write_text(HEADER + "2026-01-05T09:30:00Z,10,11,9,10,100\n"
                            "2026-01-05T11:30:00Z,10,11,9,10,100\n", encoding="utf-8")
            expected = {utc_timestamp("2026-01-05T09:30:00Z"),
                        utc_timestamp("2026-01-05T10:30:00Z"),
                        utc_timestamp("2026-01-05T11:30:00Z")}
            status, message = audit_file(path, 2, start=min(expected), end=max(expected), expected=expected)
            self.assertEqual(status, "WARN")
            self.assertIn("missing 1 expected bars", message)
            self.assertNotIn("endpoints", message)
            status, message = audit_file(path, 2, start=min(expected), end=utc_timestamp("2026-01-05T12:30:00Z"))
            self.assertEqual(status, "WARN")
            self.assertIn("requested endpoints", message)
            path.write_text(HEADER + "2026-01-05T09:30:00,10,11,9,10,100\n", encoding="utf-8")
            self.assertEqual(audit_file(path, 1, expected=expected)[0], "ERROR")

    def test_expected_symbols_and_schedule_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "ABC.csv").write_text(HEADER + "2026-03-09T13:30:00Z,10,11,9,10,100\n", encoding="utf-8")
            symbols = data / "symbols.csv"
            symbols.write_text("symbol\nABC\nMISSING\n", encoding="utf-8")
            schedule = data / "schedule.csv"
            schedule.write_text("symbol,timestamp\nABC,2026-03-09T09:30:00-04:00\n", encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(data), "--min-rows", "1",
                   "--symbols", str(symbols), "--schedule", str(schedule), "--strict"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("ABC          PASS", result.stdout)
            self.assertIn("MISSING      ERROR   expected symbol file missing", result.stdout)
            self.assertNotIn("schedule     ", result.stdout)
            schedule.write_text("symbol,timestamp\nABC,2026-03-09T09:30:00\n", encoding="utf-8")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            schedule.write_text("symbol,timestamp\nABC,2026-03-09T13:30:00Z\nABC,2026-03-09T09:30:00-04:00\n", encoding="utf-8")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            symbols.write_text("symbol\nABC\nABC\n", encoding="utf-8")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)

    def test_coverage_arguments_and_missing_schedule(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            (data / "ABC.csv").write_text(HEADER + "2026-01-05T09:30:00Z,10,11,9,10,100\n", encoding="utf-8")
            (data / "DEF.csv").write_text(HEADER + "2026-01-05T09:30:00Z,10,11,9,10,100\n", encoding="utf-8")
            schedule = root / "schedule.csv"
            schedule.write_text("symbol,timestamp\nABC,2026-01-05T09:30:00Z\n", encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(data), "--min-rows", "1"]
            self.assertEqual(subprocess.run(cmd + ["--start", "2026-01-05T09:30:00Z"], capture_output=True).returncode, 2)
            result = subprocess.run(cmd + ["--schedule", str(schedule), "--strict"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertIn("no expected schedule for symbol", result.stdout)

    def test_empty_input_directory_and_missing_file_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            symbols = root / "symbols.csv"
            symbols.write_text("symbol\nABC\n", encoding="utf-8")
            report = root / "report.csv"
            cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(data),
                   "--symbols", str(symbols), "--csv-report", str(report), "--strict"]
            result = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1, result.stderr)
            self.assertIn("ABC,,ERROR,expected symbol file missing", report.read_text(encoding="utf-8"))

    def test_invalid_schedule_and_reversed_endpoints(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            symbols = root / "symbols.csv"
            symbols.write_text("symbol\nABC\n", encoding="utf-8")
            schedule = root / "schedule.csv"
            schedule.write_text("symbol,timestamp\nABC\n", encoding="utf-8")
            cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(root),
                   "--symbols", str(symbols), "--schedule", str(schedule)]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            schedule.write_text("symbol,timestamp\nXYZ,2026-01-01T00:00:00Z\n", encoding="utf-8")
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)
            cmd = [sys.executable, str(ROOT / "audit_market_data.py"), str(root), "--symbols", str(symbols),
                   "--start", "2026-01-02T00:00:00Z", "--end", "2026-01-01T00:00:00Z"]
            self.assertEqual(subprocess.run(cmd, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
