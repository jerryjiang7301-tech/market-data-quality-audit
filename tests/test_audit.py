import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audit_market_data import audit_file

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


if __name__ == "__main__":
    unittest.main()
