# Unit Tests

Unit tests for `fuel_alert.py`, covering the configurable parts of the
price-alert logic. They're written with Python's built-in `unittest`, so the
suite runs with **no extra dependencies**.

## Running the tests

From the project root:

```bash
# Run the whole suite
python3 -m unittest discover -s tests

# Verbose (lists each test)
python3 -m unittest discover -s tests -v

# Run a single module
python3 -m unittest tests.test_should_send_alert -v
```

### With pytest (optional)

The same tests also run under [pytest](https://docs.pytest.org/), which gives
nicer output and test filtering. Install the dev dependency with
[uv](https://docs.astral.sh/uv/) first:

```bash
# Install pytest into the project's .venv
uv pip install -r requirements-dev.txt

# Run the whole suite
python3 -m pytest tests/ -v

# Run a single module, or filter by name
python3 -m pytest tests/test_should_send_alert.py -v
python3 -m pytest tests/ -k threshold
```

The `tests/__init__.py` adds the project root to `sys.path`, so the tests can
`import fuel_alert` no matter where the runner (unittest or pytest) is launched
from.

## What's covered

The tests target the small, pure functions that hold the feature logic. Each is
independently testable and has no network, database, or Google Sheets
dependency.

| File | Function under test | What it verifies |
|------|--------------------|------------------|
| `test_split_field.py` | `split_field` | Splitting multi-value cells on `FIELD_DELIMITER`: trimming, dropping blanks, numeric input, and honouring a changed delimiter. |
| `test_parse_alert_threshold.py` | `parse_alert_threshold` | Converting the `Alert Threshold ($/L)` cell (dollars) to cents/L; blank/invalid/negative → `None`; invalid values are logged. |
| `test_should_send_alert.py` | `should_send_alert` | The alert decision: no-threshold = any change; threshold boundary (9.9 quiet, 10.0 alerts); drops counted; zero threshold = any change. |
| `test_real_sheet_rows.py` | all of the above | End-to-end over the two configured stations (2608 with a `0.1` threshold, 2707 blank), combining cell parsing with the alert decision. |

## Assumptions

- Tests assume the **default delimiter** (a comma). `FIELD_DELIMITER` is read
  from `.env`; the one test that needs a different delimiter overrides the
  module global and restores it afterwards.
- The "real sheet rows" values mirror the live `Alert-Locations` tab. If you
  change that data substantially, update `test_real_sheet_rows.py` to match.

## Adding new tests

1. Add a `test_*.py` module under `tests/` (it's auto-discovered).
2. Import the function under test from `fuel_alert`.
3. Prefer testing **pure functions**. If new logic lives inline inside
   `main()`, extract it into a small named function first (as was done for
   `split_field`, `parse_alert_threshold`, and `should_send_alert`) so it can be
   tested without mocking the network or Google Sheets.
