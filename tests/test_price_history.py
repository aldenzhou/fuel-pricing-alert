"""Tests for the price_history trend-tracking schema and helpers.

Covers init_db creating the new tables, record_price_history appending readings,
and the one-time backfill seeding price_history from existing `prices` baselines
without re-running on subsequent init_db calls.
"""

import logging
import os
import sqlite3
import tempfile
import unittest
from datetime import datetime

import fuel_alert
from fuel_alert import init_db, logger, record_price_history

# init_db / backfill log via the 'fuel_alert' logger; keep it quiet in tests.
logger.addHandler(logging.NullHandler())


class PriceHistoryTestCase(unittest.TestCase):
    """Base class: point DB_FILE at a fresh temp database for each test."""

    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db_path)  # let sqlite create it fresh
        self._orig_db = fuel_alert.DB_FILE
        fuel_alert.DB_FILE = self.db_path

    def tearDown(self):
        fuel_alert.DB_FILE = self._orig_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def table_names(self, conn):
        return {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}


class TestSchema(PriceHistoryTestCase):
    def test_init_db_creates_new_tables(self):
        conn = init_db()
        try:
            names = self.table_names(conn)
            self.assertIn("price_history", names)
            self.assertIn("stations", names)
        finally:
            conn.close()

    def test_init_db_is_idempotent(self):
        # Running twice must not error or duplicate.
        init_db().close()
        conn = init_db()
        conn.close()


class TestRecordPriceHistory(PriceHistoryTestCase):
    def test_record_appends_row(self):
        conn = init_db()
        try:
            c = conn.cursor()
            ts = datetime.now().isoformat(timespec="seconds")
            record_price_history(c, "2608", "Ampol Thornleigh", "U91", 189.9, ts)
            conn.commit()
            rows = c.execute(
                "SELECT station_code, station_name, fuel_type, price, recorded_at "
                "FROM price_history").fetchall()
            self.assertEqual(rows, [("2608", "Ampol Thornleigh", "U91", 189.9, ts)])
        finally:
            conn.close()

    def test_records_accumulate_as_time_series(self):
        conn = init_db()
        try:
            c = conn.cursor()
            record_price_history(c, "2608", "Ampol", "U91", 189.9, "2026-06-25T08:00:00")
            record_price_history(c, "2608", "Ampol", "U91", 199.9, "2026-06-26T08:00:00")
            conn.commit()
            prices = [r[0] for r in c.execute(
                "SELECT price FROM price_history WHERE station_code='2608' "
                "AND fuel_type='U91' ORDER BY recorded_at").fetchall()]
            self.assertEqual(prices, [189.9, 199.9])
        finally:
            conn.close()


class TestBackfill(PriceHistoryTestCase):
    def _seed_prices(self, rows):
        """Create a DB with only a populated `prices` table, no price_history."""
        conn = sqlite3.connect(self.db_path)
        conn.execute(
            "CREATE TABLE prices (station_code TEXT, fuel_type TEXT, price REAL, "
            "PRIMARY KEY (station_code, fuel_type))")
        conn.executemany(
            "INSERT INTO prices VALUES (?, ?, ?)", rows)
        conn.commit()
        conn.close()

    def test_backfill_seeds_from_existing_prices(self):
        self._seed_prices([("2608", "U91", 189.9), ("2707", "E10", 179.9)])
        conn = init_db()
        try:
            count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
            self.assertEqual(count, 2)
            # Backfilled rows carry the live prices.
            prices = sorted(r[0] for r in conn.execute(
                "SELECT price FROM price_history").fetchall())
            self.assertEqual(prices, [179.9, 189.9])
        finally:
            conn.close()

    def test_backfill_runs_only_once(self):
        self._seed_prices([("2608", "U91", 189.9)])
        init_db().close()                       # first run backfills
        conn = init_db()                        # second run must not duplicate
        try:
            count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
            self.assertEqual(count, 1)
        finally:
            conn.close()

    def test_no_backfill_when_prices_empty(self):
        conn = init_db()  # fresh DB, no prices
        try:
            count = conn.execute("SELECT COUNT(*) FROM price_history").fetchone()[0]
            self.assertEqual(count, 0)
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
