"""Add NSW fuel stations to the 'Alert-Locations' sheet by suburb.

Reads the 'All-Locations' reference sheet (populated by
``fuel_alert.py --update-locations``), finds every station whose address suburb
exactly matches one of the suburbs passed on the command line, and appends the
new ones to the 'Alert-Locations' sheet.

Usage:
    .venv/bin/python add_alert_locations.py Hornsby Waitara "Pennant Hills"
    .venv/bin/python add_alert_locations.py --dry-run Chatswood
    .venv/bin/python add_alert_locations.py --chat-ids 12345,67890 Epping

New rows reuse the Fuel Types convention from the sheet by default. The Telegram
Chat ID(s) come from DEFAULT_ALERT_CHAT_IDS in .env, or pass --chat-ids; both
can be overridden along with --fuel-types / --threshold.

Suburb matching is exact (case-insensitive), so "Hornsby" will NOT pull in
"Hornsby Heights", and "Pennant Hills" will NOT pull in "West Pennant Hills".
Stations already present in 'Alert-Locations' (by Station Code) are skipped.
"""

import os
import argparse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Single source of truth for suburb parsing; defined in fuel_alert so the price
# checker and this tool can never drift apart.
from fuel_alert import extract_suburb

load_dotenv()

GOOGLE_CREDS_FILE = os.getenv('GOOGLE_CREDS_FILE', 'keys/google_credentials.json')
SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

# Defaults mirror the convention already used in the 'Alert-Locations' sheet so
# appended rows immediately produce alerts. Override on the command line.
# The Telegram Chat ID(s) are read from the environment (never hardcoded); set
# DEFAULT_ALERT_CHAT_IDS in .env or pass --chat-ids on the command line.
DEFAULT_FUEL_TYPES = os.getenv('DEFAULT_FUEL_TYPES') or "E10,U91,P95,P98,DL,PDL,LPG"
DEFAULT_CHAT_IDS = os.getenv('DEFAULT_ALERT_CHAT_IDS', '')
DEFAULT_THRESHOLD = ""


def open_spreadsheet(client):
    """Open the configured spreadsheet, falling back to a Drive file lookup.

    ``gspread.Client.open`` occasionally raises SpreadsheetNotFound even when the
    service account can see the file, so fall back to matching by name in the
    Drive file listing.
    """
    try:
        return client.open(SHEET_NAME)
    except Exception:
        for f in client.list_spreadsheet_files():
            if f.get('name') == SHEET_NAME:
                return client.open_by_key(f['id'])
        raise


def as_text(value):
    """Prefix a value with an apostrophe so Sheets stores it as text.

    Station Codes and (especially long) Telegram Chat IDs must be kept as text;
    stored as numbers they can lose precision or render in scientific notation.
    The leading apostrophe is honoured by value_input_option='USER_ENTERED' and
    is not shown in the cell. Blank values are left blank.
    """
    value = str(value).strip()
    return f"'{value}" if value else value


def find_new_rows(spreadsheet, wanted_suburbs, fuel_types, chat_ids, threshold):
    """Return the rows to append for stations in the wanted suburbs.

    Skips stations whose code is already in 'Alert-Locations' and de-duplicates
    repeated codes within this run.
    """
    want = {s.strip().upper() for s in wanted_suburbs}

    all_rows = spreadsheet.worksheet("All-Locations").get_all_records()
    alert_rows = spreadsheet.worksheet("Alert-Locations").get_all_records()
    seen = {str(r['Station Code']).strip() for r in alert_rows}

    new_rows = []
    for r in all_rows:
        code = str(r.get('Station Code', '')).strip()
        suburb = extract_suburb(r.get('Address', ''))
        if not code or not suburb or suburb.upper() not in want:
            continue
        if code in seen:
            continue
        seen.add(code)
        new_rows.append([
            as_text(code),
            r.get('Name', ''),
            fuel_types,
            as_text(chat_ids),
            threshold,
        ])
    return new_rows


def main():
    parser = argparse.ArgumentParser(
        description="Add NSW stations to the 'Alert-Locations' sheet by suburb.")
    parser.add_argument("suburbs", nargs="+",
                        help="One or more suburb names (quote multi-word suburbs).")
    parser.add_argument("--fuel-types", default=DEFAULT_FUEL_TYPES,
                        help=f"Fuel Types cell value (default: {DEFAULT_FUEL_TYPES}).")
    parser.add_argument("--chat-ids", default=DEFAULT_CHAT_IDS,
                        help="Telegram Chat IDs cell value "
                             "(default: DEFAULT_ALERT_CHAT_IDS from .env).")
    parser.add_argument("--threshold", default=DEFAULT_THRESHOLD,
                        help="Alert Threshold ($/L) cell value (default: blank).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be added without writing to the sheet.")
    args = parser.parse_args()

    if not SHEET_NAME:
        raise SystemExit("GOOGLE_SHEET_NAME is not set; check your .env file.")

    if not args.chat_ids.strip():
        raise SystemExit(
            "No Telegram Chat IDs provided. Set DEFAULT_ALERT_CHAT_IDS in .env "
            "or pass --chat-ids; otherwise the new rows would never alert.")

    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, SCOPE)
    client = gspread.authorize(creds)
    spreadsheet = open_spreadsheet(client)

    new_rows = find_new_rows(spreadsheet, args.suburbs,
                             args.fuel_types, args.chat_ids, args.threshold)

    print(f"Suburbs: {', '.join(args.suburbs)}")
    print(f"New stations to add: {len(new_rows)}")
    for row in new_rows:
        # row[0]/row[3] carry a leading apostrophe; strip it for display.
        print(f"  {row[0].lstrip(chr(39)):>6} | {row[1]}")

    if not new_rows:
        print("Nothing to add.")
        return

    if args.dry_run:
        print("\nDry run: no changes written.")
        return

    spreadsheet.worksheet("Alert-Locations").append_rows(
        new_rows, value_input_option='USER_ENTERED')
    print(f"\nAppended {len(new_rows)} rows to 'Alert-Locations'.")


if __name__ == "__main__":
    main()
