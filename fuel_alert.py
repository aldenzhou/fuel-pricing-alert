import os
import sqlite3
import requests
import uuid
import argparse
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
DB_FILE = 'fuel_prices.db'
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
BASE_URL = "https://api.onegov.nsw.gov.au/FuelPriceCheck/v1/fuel/prices/station/"

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
        print(f"Failed to get token. Status: {response.status_code}")
        print(f"Response text: {response.text}")
        raise e
    access_token = token_data['access_token']
    expires_in = int(token_data['expires_in'])

    c.execute("DELETE FROM auth")
    c.execute("INSERT INTO auth (token, expires_at) VALUES (?, ?)",
              (access_token, now + expires_in))
    conn.commit()

    return access_token

def get_station_prices(station_code, token):
    """Fetch current prices for a specific station from NSW API."""
    url = f"{BASE_URL}{station_code}"

    # API.NSW requires a very specific timestamp format
    timestamp = datetime.now().strftime('%d/%m/%Y %I:%M:%S %p')

    headers = {
        "Authorization": f"Bearer {token}",
        "apikey": NSW_API_KEY,
        "transactionid": str(uuid.uuid4()),
        "requesttimestamp": timestamp
    }

    try:
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
    except requests.RequestException as e:
        print(f"[{datetime.now()}] Request error fetching prices for station {station_code}: {e}")
        return []

    if response.status_code == 200:
        return response.json().get('prices', [])

    print(f"[{datetime.now()}] Failed to fetch prices for station {station_code}. "
          f"Status: {response.status_code}, Response: {response.text}")
    return []

def send_telegram_message(chat_id, message, parse_mode="Markdown"):
    """Send message via Telegram Bot."""
    if not TELEGRAM_BOT_TOKEN:
        print(f"Telegram not configured. Would have sent to {chat_id}: {message}")
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
        print(f"Sent Telegram message to {chat_id}")
    except Exception as e:
        print(f"Failed to send Telegram message to {chat_id}: {e}")
        if 'response' in locals():
            print(f"Response: {response.text}")

def notify_developer(message):
    """Send a technical failure notification to the developer chat only.

    Sent as plain text (no Markdown) so raw error strings can't break parsing.
    End users never receive these messages.
    """
    if not DEVELOPER_CHAT_ID:
        print(f"[{datetime.now()}] DEVELOPER_CHAT_ID not set; skipping developer alert.")
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
        print(f"[{datetime.now()}] Invalid 'Alert Threshold ($/L)' value "
              f"'{raw_value}' for {station_name}{fuel_label}; treating as blank "
              f"(alert on any change).")
        return None

    if dollars < 0:
        print(f"[{datetime.now()}] Negative 'Alert Threshold ($/L)' value "
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

def format_alert_message(fuel_type, station_name, old_price, new_price):
    """Build the Telegram alert text for a price change.

    Shared by the live run and the manual simulation harness so both produce
    identical messages.
    """
    direction = "dropped" if new_price < old_price else "increased"
    return (f"⛽ *Fuel Alert*\n{fuel_type} at {station_name} {direction} "
            f"from {old_price} to {new_price} c/L.")

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

    print(f"[{datetime.now()}] Updating 'All-Locations' sheet with latest stations...")
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
                print("No stations found in the API response.")
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
            print(f"[{datetime.now()}] Successfully updated 'All-Locations' sheet with {len(station_list)} stations.")
        else:
            print(f"[{datetime.now()}] Failed to fetch reference data. Status: {response.status_code}")
            notify_developer(f"⚠️ Fuel alert: failed to update 'All-Locations' sheet. "
                             f"Reference data request returned status {response.status_code}.")
    except Exception as e:
        print(f"[{datetime.now()}] Error updating 'All-Locations' sheet: {e}")
        notify_developer(f"⚠️ Fuel alert: error updating 'All-Locations' sheet: {e}")

def main(update_locations=False):
    print(f"[{datetime.now()}] Starting fuel price check...")
    conn = init_db()
    c = conn.cursor()

    try:
        token = get_nsw_token(conn)

        # Update the All-Locations reference sheet only when explicitly requested
        if update_locations:
            update_all_locations_sheet(token, conn)

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

            # Fetch current prices from API
            current_prices_data = get_station_prices(station_code, token)

            # Convert API response to a dictionary of {fuel_type: price}
            current_prices = {
                item['fueltype']: item['price']
                for item in current_prices_data
            }

            for fuel_type in target_fuels:
                if fuel_type in current_prices:
                    new_price = float(current_prices[fuel_type])

                    # Check previous price in SQLite
                    c.execute("SELECT price FROM prices WHERE station_code=? AND fuel_type=?",
                              (station_code, fuel_type))
                    row = c.fetchone()

                    if row is None:
                        # First time seeing this price, just save it, don't alert
                        print(f"Initial price for {station_name} ({fuel_type}): {new_price}")
                        c.execute("INSERT INTO prices (station_code, fuel_type, price) VALUES (?, ?, ?)",
                                  (station_code, fuel_type, new_price))
                    elif row[0] != new_price:
                        old_price = row[0]
                        # Price changed. Always refresh the stored baseline so the
                        # next comparison is against the most recent reading.
                        print(f"Price change detected for {station_name} ({fuel_type}): {old_price} -> {new_price}")
                        c.execute("UPDATE prices SET price=? WHERE station_code=? AND fuel_type=?",
                                  (new_price, station_code, fuel_type))

                        # Only alert when the move meets the location's threshold.
                        if not should_send_alert(old_price, new_price, threshold_cents):
                            print(f"Change for {station_name} ({fuel_type}) below threshold "
                                  f"({abs(new_price - old_price):.1f} < {threshold_cents:.1f} c/L); no alert sent.")
                        else:
                            msg = format_alert_message(fuel_type, station_name, old_price, new_price)

                            for chat_id in target_chats:
                                send_telegram_message(chat_id, msg)

        conn.commit()
        print(f"[{datetime.now()}] Check completed successfully.")
    except Exception as e:
        print(f"[{datetime.now()}] Error running fuel alert: {e}")
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
    main(update_locations=cli_args.update_locations)
