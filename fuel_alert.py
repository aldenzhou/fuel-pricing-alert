import os
import sys
import sqlite3
import requests
import uuid
import argparse
import logging
import gspread
from datetime import datetime
from logging.handlers import RotatingFileHandler
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
# Resolve paths relative to this file so cron runs and manual runs (which may
# have different working directories) always read/write the same locations.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = 'fuel_prices.db'

# Rotating log file. Logs live in a dedicated 'logs/' folder and roll over at
# ~1 MB, keeping 5 old files (~6 MB total) so a long-running cron can never fill
# the disk. See setup_logging().
LOG_DIR = os.path.join(BASE_DIR, 'logs')
LOG_FILE = os.path.join(LOG_DIR, 'fuel_alert.log')
LOG_MAX_BYTES = 1_000_000
LOG_BACKUP_COUNT = 5

logger = logging.getLogger("fuel_alert")
# Delimiter used to separate multiple values within a single Google Sheet cell
# (e.g. several fuel types or chat IDs in one cell). Configurable via .env;
# defaults to a comma when unset or blank.
FIELD_DELIMITER = os.getenv('FIELD_DELIMITER') or ','
GOOGLE_CREDS_FILE = os.getenv('GOOGLE_CREDS_FILE', 'keys/google_credentials.json')
SHEET_NAME = os.getenv('GOOGLE_SHEET_NAME')

# Network timeout (seconds) applied to every outbound HTTP request so a hung
# API can never stall a cron run indefinitely.
REQUEST_TIMEOUT = 30

# Telegram Setup
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
# Chat ID that receives technical failure notifications. End users never see
# these; leave unset to disable developer alerts.
DEVELOPER_CHAT_ID = os.getenv('DEVELOPER_CHAT_ID')

# NSW API Setup
NSW_API_KEY = os.getenv('NSW_API_KEY')
NSW_AUTH_HEADER = os.getenv('NSW_AUTH_HEADER')
AUTH_URL = "https://api.onegov.nsw.gov.au/oauth/client_credential/accesstoken"
# "Get all prices" endpoint: returns a full snapshot of every NSW station's
# current prices in a single request. We fetch this once per run and filter
# locally, instead of hitting the per-station endpoint once per monitored
# location — so API quota usage no longer scales with the number of stations
# being watched. (Note: do NOT use /fuel/prices/new, which returns only a
# differential of changes since the last call and would miss baselines.)
ALL_PRICES_URL = "https://api.onegov.nsw.gov.au/FuelPriceCheck/v1/fuel/prices"

def setup_logging():
    """Configure logging to a rotating file in logs/ plus the console.

    The file handler rotates at LOG_MAX_BYTES and keeps LOG_BACKUP_COUNT old
    files, so unattended cron runs can't grow the log without bound. A stream
    handler on stdout keeps manual runs readable; under cron, stdout is
    discarded (the rotating file is the record) and only stderr is captured.
    """
    os.makedirs(LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT,
        encoding="utf-8")
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)

    logger.setLevel(logging.INFO)
    # Replace any existing handlers so repeated calls don't duplicate output.
    logger.handlers.clear()
    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)
    logger.propagate = False


def init_db():
    """Initialize SQLite database for storing prices and API tokens."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS prices
                 (station_code TEXT, fuel_type TEXT, price REAL,
                 PRIMARY KEY (station_code, fuel_type))''')
    c.execute('''CREATE TABLE IF NOT EXISTS auth
                 (token TEXT, expires_at REAL)''')
    c.execute('''CREATE TABLE IF NOT EXISTS metadata
                 (key TEXT PRIMARY KEY, value TEXT)''')
    conn.commit()
    return conn

def get_nsw_token(conn):
    """Get OAuth token, using cached version if still valid."""
    c = conn.cursor()
    c.execute("SELECT token, expires_at FROM auth LIMIT 1")
    row = c.fetchone()

    now = datetime.now().timestamp()
    if row and row[1] > now + 300: # Valid for at least 5 more minutes
        return row[0]

    # Fetch new token using the provided Authorization Header
    headers = {
        "Authorization": NSW_AUTH_HEADER
    }

    # API.NSW expects the grant_type in the URL query parameters for this specific endpoint
    auth_url_with_params = f"{AUTH_URL}?grant_type=client_credentials"

    response = requests.get(auth_url_with_params, headers=headers, timeout=REQUEST_TIMEOUT)

    try:
        response.raise_for_status()
        token_data = response.json()
    except Exception as e:
        logger.error(f"Failed to get token. Status: {response.status_code}")
        logger.error(f"Response text: {response.text}")
        raise e
    access_token = token_data['access_token']
    expires_in = int(token_data['expires_in'])

    c.execute("DELETE FROM auth")
    c.execute("INSERT INTO auth (token, expires_at) VALUES (?, ?)",
              (access_token, now + expires_in))
    conn.commit()

    return access_token

def get_all_prices(token):
    """Fetch current prices for ALL NSW stations in a single API call.

    Replaces the previous per-station polling: one request to the FuelCheck
    "get all prices" endpoint returns every station's current prices, which we
    then index by station code and filter locally. This keeps each run to a
    single price API call (plus the cached token) regardless of how many
    locations are being monitored.

    Returns a dict mapping ``station_code`` (str) to a ``{fueltype: price}``
    dict. Returns None when the request fails, so the caller can skip the run
    rather than mistaking a fetch failure for "no prices" — which would silently
    suppress alerts but, importantly, can never raise a false one.
    """
    # API.NSW requires a very specific timestamp format
    timestamp = datetime.now().strftime('%d/%m/%Y %I:%M:%S %p')

    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": NSW_API_KEY,
        "transactionid": str(uuid.uuid4()),
        "requesttimestamp": timestamp
    }

    try:
        response = requests.get(ALL_PRICES_URL, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        logger.error(f"Request error fetching all prices: {e}")
        return None

    if response.status_code != 200:
        logger.error(f"Failed to fetch all prices. "
                     f"Status: {response.status_code}, Response: {response.text}")
        return None

    # The all-prices endpoint tags each price entry with its 'stationcode'
    # (unlike the per-station endpoint, where the station was implicit).
    prices_by_station = {}
    for item in response.json().get('prices', []):
        code = str(item.get('stationcode', '')).strip()
        fuel_type = item.get('fueltype')
        if not code or fuel_type is None:
            continue
        prices_by_station.setdefault(code, {})[fuel_type] = item['price']

    return prices_by_station

def send_telegram_message(chat_id, message, parse_mode="Markdown"):
    """Send message via Telegram Bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.warning(f"Telegram not configured. Would have sent to {chat_id}: {message}")
        return

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode
    }

    try:
        response = requests.post(url, json=payload, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        logger.info(f"Sent Telegram message to {chat_id}")
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        if 'response' in locals():
            logger.error(f"Response: {response.text}")

def notify_developer(message):
    """Send a technical failure notification to the developer chat only.

    Sent as plain text (no Markdown) so raw error strings can't break parsing.
    End users never receive these messages.
    """
    if not DEVELOPER_CHAT_ID:
        logger.info("DEVELOPER_CHAT_ID not set; skipping developer alert.")
        return
    send_telegram_message(DEVELOPER_CHAT_ID, message, parse_mode=None)

def split_field(raw_value):
    """Split a multi-value sheet cell into a clean list of values.

    Values are separated by FIELD_DELIMITER (configurable via .env). Surrounding
    whitespace is trimmed and empty entries are dropped, so a blank cell or
    trailing delimiters yield an empty list.
    """
    return [item.strip() for item in str(raw_value).split(FIELD_DELIMITER) if item.strip()]

def parse_alert_threshold(raw_value, station_name, fuel_label=""):
    """Parse the optional per-location alert threshold.

    The sheet value is entered in dollars per litre (e.g. 0.10 = a 10 c/L move),
    while prices are stored in cents per litre, so the value is multiplied by 100.

    Returns the threshold in c/L as a float, or None when no valid threshold is
    set. Blank, missing, or unparseable values return None (alert on any change)
    so a typo can never silently suppress all alerts.
    """
    text = str(raw_value).strip()
    if not text:
        return None

    try:
        dollars = float(text)
    except ValueError:
        logger.warning(f"Invalid 'Alert Threshold ($/L)' value "
                       f"'{raw_value}' for {station_name}{fuel_label}; treating as blank "
                       f"(alert on any change).")
        return None

    if dollars < 0:
        logger.warning(f"Negative 'Alert Threshold ($/L)' value "
                       f"'{raw_value}' for {station_name}{fuel_label}; treating as blank "
                       f"(alert on any change).")
        return None

    return dollars * 100

def should_send_alert(old_price, new_price, threshold_cents):
    """Decide whether a price move warrants an alert.

    Prices are in cents per litre. ``threshold_cents`` is the minimum absolute
    move (also in c/L) required to alert, or None for "alert on any change".

    Returns True when an alert should be sent. A move is never alerted when the
    price is unchanged. When a threshold is set, the absolute change must be
    greater than or equal to it.
    """
    if old_price == new_price:
        return False
    if threshold_cents is None:
        return True
    return abs(new_price - old_price) >= threshold_cents

def format_grouped_alert_message(station_name, changes):
    """Build a single Telegram alert covering all of one station's price changes.

    ``changes`` is a list of ``(fuel_type, old_price, new_price)`` tuples. Every
    fuel that moved at a station is combined into one message — so a station whose
    price changes across several fuel types produces a single notification rather
    than one message per fuel.
    """
    lines = ["⛽ *Fuel Alert*", station_name]
    for fuel_type, old_price, new_price in changes:
        direction = "dropped" if new_price < old_price else "increased"
        lines.append(f"{fuel_type} {direction} from {old_price} to {new_price} c/L.")
    return "\n".join(lines)

def format_alert_message(fuel_type, station_name, old_price, new_price):
    """Build the Telegram alert text for a single price change.

    A thin wrapper over format_grouped_alert_message for the one-fuel case, so the
    live run and the manual simulation harness produce identical formatting.
    """
    return format_grouped_alert_message(station_name, [(fuel_type, old_price, new_price)])

def get_locations_from_sheet():
    """Read configuration from Google Sheets."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
    client = gspread.authorize(creds)

    sheet = client.open(SHEET_NAME).worksheet("Alert-Locations")
    # Skip header row
    return sheet.get_all_records()

def update_all_locations_sheet(token, conn):
    """Fetch all stations from NSW API and populate the All-Locations sheet.

    Only runs when the script is invoked with the --update-locations flag.
    """
    c = conn.cursor()
    today_str = datetime.now().strftime('%Y-%m-%d')

    logger.info("Updating 'All-Locations' sheet with latest stations...")
    # The public API endpoint for reference data
    url = "https://api.onegov.nsw.gov.au/FuelCheckRefData/v2/fuel/lovs"
    timestamp = datetime.now().strftime('%d/%m/%Y %I:%M:%S %p')

    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": NSW_API_KEY,
        "transactionid": str(uuid.uuid4()),
        "requesttimestamp": timestamp
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            data = response.json()

            # The v2 API returns a list of stations directly, or inside a 'stations' key
            # Let's inspect the actual structure
            if isinstance(data, dict):
                if 'stations' in data and isinstance(data['stations'], dict) and 'items' in data['stations']:
                    station_list = data['stations']['items']
                elif 'stations' in data and isinstance(data['stations'], list):
                    station_list = data['stations']
                elif 'items' in data and isinstance(data['items'], list):
                    station_list = data['items']
                else:
                    station_list = []
            elif isinstance(data, list):
                station_list = data
            else:
                station_list = []

            if not station_list:
                logger.warning("No stations found in the API response.")
                return

            # Prepare data for Google Sheets
            sheet_data = [["Station Code", "Brand", "Name", "Address"]]
            for s in station_list:
                if isinstance(s, dict):
                    sheet_data.append([
                        str(s.get('code', s.get('stationcode', ''))),
                        str(s.get('brand', '')),
                        str(s.get('name', '')),
                        str(s.get('address', ''))
                    ])

            # Update Google Sheet
            scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
            creds = ServiceAccountCredentials.from_json_keyfile_name(GOOGLE_CREDS_FILE, scope)
            client = gspread.authorize(creds)

            worksheet = client.open(SHEET_NAME).worksheet("All-Locations")
            worksheet.clear()

            # gspread 6.x signature
            worksheet.update(values=sheet_data, range_name='A1')

            # Record the update in SQLite
            c.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_lovs_update', ?)", (today_str,))
            conn.commit()
            logger.info(f"Successfully updated 'All-Locations' sheet with {len(station_list)} stations.")
        else:
            logger.error(f"Failed to fetch reference data. Status: {response.status_code}")
            notify_developer(f"⚠️ Fuel alert: failed to update 'All-Locations' sheet. "
                             f"Reference data request returned status {response.status_code}.")
    except Exception as e:
        logger.error(f"Error updating 'All-Locations' sheet: {e}")
        notify_developer(f"⚠️ Fuel alert: error updating 'All-Locations' sheet: {e}")

def main(update_locations=False):
    logger.info("Starting fuel price check...")
    conn = init_db()
    c = conn.cursor()

    try:
        token = get_nsw_token(conn)

        # Update the All-Locations reference sheet only when explicitly requested
        if update_locations:
            update_all_locations_sheet(token, conn)

        # Fetch every station's current prices in one request, then filter
        # locally. A None result means the fetch failed; skip this run rather
        # than treating every station as "no price" (which is harmless but
        # pointless work). The next cron run self-heals.
        all_prices = get_all_prices(token)
        if all_prices is None:
            logger.warning("Skipping price comparison this run "
                           "(could not fetch prices).")
            return

        # Fetch locations to monitor
        locations = get_locations_from_sheet()

        for loc in locations:
            station_code = str(loc.get('Station Code', '')).strip()
            station_name = loc.get('Station Name', f"Station {station_code}")

            if not station_code:
                continue

            # Parse delimited fields (see FIELD_DELIMITER)
            target_fuels = split_field(loc.get('Fuel Types', ''))

            # Support both old 'Mobile Numbers' column and new 'Telegram Chat IDs' column
            raw_chats = loc.get('Telegram Chat IDs', loc.get('Mobile Numbers', ''))
            target_chats = split_field(raw_chats)

            if not target_fuels or not target_chats:
                continue

            # Optional per-location minimum price change required to trigger an
            # alert. Entered in dollars/L in the sheet; returned here in c/L.
            # None means "alert on any change".
            threshold_cents = parse_alert_threshold(
                loc.get('Alert Threshold ($/L)', ''), station_name)

            # Look up this station's prices from the single batched fetch.
            current_prices = all_prices.get(station_code, {})

            # Collect every alert-worthy fuel move for this station so they can be
            # delivered as one combined message instead of one message per fuel.
            station_changes = []  # list of (fuel_type, old_price, new_price)

            for fuel_type in target_fuels:
                if fuel_type in current_prices:
                    new_price = float(current_prices[fuel_type])

                    # Check previous price in SQLite
                    c.execute("SELECT price FROM prices WHERE station_code=? AND fuel_type=?",
                              (station_code, fuel_type))
                    row = c.fetchone()

                    if row is None:
                        # First time seeing this price, just save it, don't alert
                        logger.info(f"Initial price for {station_name} ({fuel_type}): {new_price}")
                        c.execute("INSERT INTO prices (station_code, fuel_type, price) VALUES (?, ?, ?)",
                                  (station_code, fuel_type, new_price))
                    elif row[0] != new_price:
                        old_price = row[0]
                        # Price changed. Always refresh the stored baseline so the
                        # next comparison is against the most recent reading.
                        logger.info(f"Price change detected for {station_name} ({fuel_type}): {old_price} -> {new_price}")
                        c.execute("UPDATE prices SET price=? WHERE station_code=? AND fuel_type=?",
                                  (new_price, station_code, fuel_type))

                        # Only alert when the move meets the location's threshold.
                        if not should_send_alert(old_price, new_price, threshold_cents):
                            logger.info(f"Change for {station_name} ({fuel_type}) below threshold "
                                        f"({abs(new_price - old_price):.1f} < {threshold_cents:.1f} c/L); no alert sent.")
                        else:
                            station_changes.append((fuel_type, old_price, new_price))

            # Send a single message per station covering all of its changed fuels.
            if station_changes:
                msg = format_grouped_alert_message(station_name, station_changes)
                for chat_id in target_chats:
                    send_telegram_message(chat_id, msg)

        conn.commit()
        logger.info("Check completed successfully.")
    except Exception as e:
        logger.error(f"Error running fuel alert: {e}")
        # Route technical failures to the developer only; users never see these.
        notify_developer(f"🚨 Fuel alert run failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NSW fuel price alert checker.")
    parser.add_argument(
        "--update-locations",
        action="store_true",
        help="Fetch all NSW stations and (re)populate the 'All-Locations' sheet. "
             "Omit this for the regular price-check run."
    )
    cli_args = parser.parse_args()
    setup_logging()
    main(update_locations=cli_args.update_locations)
