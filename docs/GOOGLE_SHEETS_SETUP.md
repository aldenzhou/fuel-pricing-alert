# How to Create `google_credentials.json`

To allow your Python script to read a Google Sheet owned by your personal Gmail account, you need to create a **Service Account** in Google Cloud. 

Think of a Service Account as a "bot user" that works on behalf of your script. You will generate a key for this bot (`google_credentials.json`), and then you simply **share your Google Sheet with the bot's email address**, just like you would share it with a human friend.

Here is the step-by-step guide to doing this using your personal Gmail account:

### Step 1: Create a Google Cloud Project
1. Go to the [Google Cloud Console](https://console.cloud.google.com/) and log in with your personal Gmail account.
2. Accept the terms of service if prompted.
3. Click the **Select a project** dropdown at the top left (next to the Google Cloud logo) and click **New Project**.
4. Name it something like `Fuel Alert Service` and click **Create**.
5. Once created, make sure your new project is selected at the top of the screen.

### Step 2: Enable the Required APIs
1. In the left-hand menu, go to **APIs & Services** > **Library**.
2. Search for **Google Sheets API**, click on it, and click **Enable**.
3. Go back to the Library, search for **Google Drive API**, click on it, and click **Enable**. *(The Drive API is required for the script to discover the sheet by its name).*

### Step 3: Create the Service Account (The "Bot")
1. In the left-hand menu, go to **APIs & Services** > **Credentials**.
2. Click the **+ CREATE CREDENTIALS** button at the top and select **Service account**.
3. **Service account details:** Name it `fuel-bot` (or similar). Click **Create and Continue**.
4. **Grant this service account access:** You can skip this step. Click **Continue**.
5. **Grant users access:** You can skip this step too. Click **Done**.

### Step 4: Generate `google_credentials.json`
1. You will now see your new Service Account listed under the "Service Accounts" section. It will have an email address that looks like `fuel-bot@your-project-id.iam.gserviceaccount.com`. 
   * **Copy this email address right now** (you will need it in Step 5).
2. Click on the email address to open the Service Account details.
3. Go to the **Keys** tab at the top.
4. Click **Add Key** > **Create new key**.
5. Choose **JSON** and click **Create**.
6. A file will automatically download to your computer. **Rename this file to `google_credentials.json`** and place it in the `keys` folder inside your project directory.

### Step 5: Share Your Google Sheet with the Bot
This is the most important step! The bot cannot see your personal files unless you explicitly share them.

1. Open your Google Sheet using your personal Gmail account.
2. Click the big **Share** button in the top right corner.
3. Paste the **Service Account email address** (from Step 4.1) into the "Add people and groups" box.
4. Give it **Viewer** access (it only needs to read the data, not edit it).
5. Uncheck "Notify people" (since it's a bot, it doesn't check email) and click **Share**.

That's it! Your script now has the exact credentials it needs, and the bot has permission to read your specific Google Sheet.

---

# How to Structure Your Google Sheet

Your Google Sheet acts as the configuration database for your script. You must create **two tabs (worksheets)** at the bottom of your Google Sheet:
1. **`Alert-Locations`** (This is where you put the stations you want to monitor)
2. **`All-Locations`** (The script will automatically populate this with every station in NSW so you can easily look up Station Codes)

### The `Alert-Locations` Tab
Row 1 **must** contain the exact column headers the script is looking for. From Row 2 downwards, you will add your locations.

#### The Column Headers (Row 1)
Put these exactly as written in the first row:
* **Column A:** `Station Code`
* **Column B:** `Station Name`
* **Column C:** `Fuel Types`
* **Column D:** `Telegram Chat IDs`
* **Column E:** `Alert Threshold ($/L)` *(optional — may be left blank)*

### Example Data (Row 2 and below)

| Station Code | Station Name | Fuel Types | Telegram Chat IDs | Alert Threshold ($/L) |
| :--- | :--- | :--- | :--- | :--- |
| `12345` | Coles Express Waterloo | `U91,P98` | `123456789,987654321` | `0.10` |
| `67890` | 7-Eleven Surry Hills | `E10` | `123456789` | |
| `54321` | Ampol North Sydney | `DL,PDL` | `123456789,555555555` | `0.05` |

### Detailed Breakdown of Each Column

**1. Station Code**
This is the unique numeric ID that API.NSW uses to identify a specific petrol station. 
* *How to find it:* You can easily find this by looking at the **`All-Locations`** tab in your Google Sheet (which the script populates automatically). Just use `Ctrl+F` to search for the suburb or brand you want, and copy the Station Code from Column A.

**2. Station Name**
The API doesn't actually need this, but the script uses it to make your Telegram alerts readable. You can name it whatever makes sense to you (e.g., "Coles Express Waterloo" or "Cheap station near work").

**3. Fuel Types**
You must use the exact fuel codes that the NSW API uses, separated by commas `,` if you want to track more than one.
* **Common NSW Fuel Codes:**
  * `E10` (Ethanol 94)
  * `U91` (Unleaded 91)
  * `P95` (Premium 95)
  * `P98` (Premium 98)
  * `DL` (Diesel)
  * `PDL` (Premium Diesel)
  * `LPG` (LPG)
* *Example:* If you want to track Unleaded 91 and Premium 98, you write: `U91,P98`

**4. Telegram Chat IDs**
The Telegram Chat IDs of the users who should receive the message when the price changes at this specific station. 
* *How to find it:* Have the user open Telegram, search for the bot `@userinfobot` or `@getmyid_bot`, and send it a message. The bot will reply with their numeric ID (e.g., `123456789`).
* **⚠️ Important:** The user MUST start a conversation with your bot in Telegram before the bot can send them alerts. See [TELEGRAM_SETUP.md](TELEGRAM_SETUP.md) for details.
* Separate multiple IDs with commas `,`.
* *Example:* If you and your partner both want alerts for the Waterloo station, you write: `123456789,987654321`

**5. Alert Threshold ($/L)** *(optional)*
Controls how big a price change must be before an alert is sent, in **dollars per litre**.
* *Example:* `0.10` means "only alert when the price moves by at least 10 cents/L (up or down)".
* **Leave it blank** to get an alert on *any* price change (this is the default behaviour).
* Invalid or negative values are ignored and treated as blank.

> ### ⚠️ Important: how the threshold actually works
> The threshold is compared against **each individual price change**, measured from
> the *previous* recorded price. The script always updates its stored price every
> time it changes, even when the move is too small to alert.
>
> This means: **a series of small changes that each stay under the threshold will
> NEVER trigger an alert — even if they add up to a large total move.** The
> threshold only fires when a *single* change is at or above the value you set.
>
> *Example with a `0.10` (10c) threshold:*
>
> | Reading | Price | Change vs previous | Alert? |
> | :--- | :--- | :--- | :--- |
> | Start | 189.9 | — | — |
> | Next | 195.0 | +5.1c | No (under 10c) |
> | Next | 199.9 | +4.9c | No (under 10c) |
> | Next | 204.9 | +5.0c | No (under 10c) |
>
> The price rose 15c overall, but because **each step** was under 10c, no alert was
> ever sent. If you want to catch gradual creeps like this, use a smaller threshold
> or leave the column blank.

### How it works in practice based on the example above:
* If the price of **U91** changes at **Coles Express Waterloo** by **10c/L or more**, both `123456789` and `987654321` will get a Telegram message. Smaller moves are ignored because the threshold is set to `0.10`.
* If the price of **E10** changes at **7-Eleven Surry Hills** by **any amount**, only `123456789` will get a message (the threshold is blank).
* If the price of **DL** (Diesel) changes at **Ampol North Sydney** by **5c/L or more**, both `123456789` and `555555555` will get a message.
