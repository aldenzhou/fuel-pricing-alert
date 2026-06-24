# Fuel Pricing Alert Service

A Python service that polls the NSW FuelCheck API every 30 minutes, compares prices against a local SQLite database, and sends Telegram alerts when prices change. Configuration (locations, fuel types, and chat IDs) is managed via a Google Sheet.

## Deployment Instructions (Linux)

1. **Copy Files:** Copy all files in this directory to your target Linux machine.
2. **Install Dependencies:**
   ```bash
   pip3 install -r requirements.txt
   ```
3. **Configure Environment:**
   * Rename `.env.example` to `.env`
   * Fill in your Telegram Bot Token, NSW API credentials, and Google Sheet name.
   * Optionally set `DEVELOPER_CHAT_ID` to a Telegram chat that should receive technical failure notifications. These are sent only to the developer — end users never see error messages. Leave it blank to disable.
   * Optionally set `FIELD_DELIMITER` to change the character used to separate multiple values within a single sheet cell (defaults to a comma `,`).
4. **Google Credentials:**
   * Create a folder named `keys` in the project directory.
   * Place your Google Service Account JSON file in the `keys` folder and name it `google_credentials.json`.
5. **Populate the Station List (optional, one-off):**
   * Run the script with the `--update-locations` flag to fill the `All-Locations` tab with a master list of every NSW station:
     ```bash
     python3 fuel_alert.py --update-locations
     ```
   * Re-run this whenever you want to refresh the master station list.
6. **Setup Cron Job:**
   * Make the setup script executable: `chmod +x setup_cron.sh`
   * Run it to schedule the 30-minute polling: `./setup_cron.sh`

## Usage

```bash
# Regular price-check run (this is what the cron job runs)
python3 fuel_alert.py

# Refresh the 'All-Locations' master station list, then run the price check
python3 fuel_alert.py --update-locations
```

## Google Sheet Format
Your Google Sheet must contain two tabs (worksheets):
1. **`Alert-Locations`**: This is where you configure the stations you want to monitor.
2. **`All-Locations`**: A master list of all NSW stations so you can easily look up Station Codes. This tab is **only** populated when you run the script with the `--update-locations` flag — the regular (cron) runs leave it untouched.

In the **`Alert-Locations`** tab, ensure you have the following columns in Row 1:
* `Station Code` (e.g., 12345)
* `Station Name` (e.g., Coles Express Waterloo)
* `Fuel Types` (e.g., U91,P98)
* `Telegram Chat IDs` (e.g., 123456789,987654321)
* `Alert Threshold ($/L)` (optional, e.g., `0.10`)

Within a single cell, separate multiple `Fuel Types` or `Telegram Chat IDs`
with the delimiter configured by `FIELD_DELIMITER` in `.env` (a comma `,` by
default).

The `Alert Threshold ($/L)` column controls how large a price change must be
before an alert is sent, in **dollars per litre**. For example, `0.10` means
"only alert when the price moves by at least 10 c/L (up or down)". Leave the
cell **blank** to alert on any change (the default behaviour). Invalid or
negative values are treated as blank.

> **⚠️ How the threshold works:** the threshold is checked against *each
> individual price change* (measured from the previous recorded price), and the
> stored price is always updated when it changes. So **a run of small changes
> that each stay under the threshold will never trigger an alert, even if they
> add up to a large total move** — the threshold only fires when a *single*
> change is at or above the value you set. To catch gradual creeps, use a
> smaller threshold or leave the column blank. See
> [GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md) for a worked example.

## Testing

Unit tests live in the [`tests/`](tests/) folder and use Python's built-in
`unittest` (no extra dependencies). Run them from the project root:

```bash
python3 -m unittest discover -s tests -v
```

See [`tests/README.md`](tests/README.md) for what's covered and how to add more.

### Manual alert simulation

`simulate_price_changes.py` mimics realistic fuel price changes and runs them
through the real alert logic, so you can verify alerts fire and see how the
`Alert Threshold ($/L)` setting filters small moves. It does **not** touch the
database or the live NSW API.

```bash
# Dry run — print a results table, send nothing
python3 simulate_price_changes.py

# Also deliver the triggered alerts to Telegram (uses DEVELOPER_CHAT_ID)
python3 simulate_price_changes.py --send

# Send the triggered alerts to a specific chat id
python3 simulate_price_changes.py --send --chat-id 123456789
```

Each scenario carries a documented expectation, so the script exits non-zero if
the alert logic ever disagrees with it.

## Documentation

For detailed instructions on setting up the various components of this service, please refer to the following guides:
* **[GOOGLE_SHEETS_SETUP.md](docs/GOOGLE_SHEETS_SETUP.md)**: How to create the Google Cloud Service Account, generate `google_credentials.json`, and format your spreadsheet.
* **[TELEGRAM_SETUP.md](docs/TELEGRAM_SETUP.md)**: How to create your Telegram Bot, find your Chat ID, and authorize the bot to message you.
