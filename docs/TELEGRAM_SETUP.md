# How to Set Up Telegram Alerts

This service uses a Telegram Bot to send fuel price alerts directly to your phone. Follow these steps to create your bot, find your Chat ID, and configure the service.

### Step 1: Create a Telegram Bot
1. Open the Telegram app on your phone or computer.
2. Search for **@BotFather** (this is the official Telegram bot for creating other bots).
3. Send the message `/newbot` to BotFather.
4. Follow the prompts to choose a display name (e.g., "My Fuel Alerts") and a username (must end in `bot`, e.g., `MyFuelAlertsBot`).
5. BotFather will reply with a **Bot Token** (it looks something like `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`).
6. Open your `.env` file on your server and paste this token:
   `TELEGRAM_BOT_TOKEN=your_token_here`

### Step 2: Get Your Chat ID
To send a message to a specific person, the bot needs their unique numeric Telegram Chat ID.
1. In Telegram, search for the bot **@userinfobot** (or **@getmyid_bot**).
2. Send it any message (like "hello" or `/start`).
3. It will reply with your numeric `Id` (e.g., `123456789`).
4. Put this number in the **`Telegram Chat IDs`** column of your `Alert-Locations` Google Sheet.

### Step 3: ⚠️ CRITICAL: Start the Bot! ⚠️
Telegram has a strict anti-spam rule: **Bots cannot initiate conversations with users.** A bot can only send you a message *after* you have messaged it first.

Before the script can send you any alerts, you (and anyone else whose Chat ID is in the Google Sheet) **MUST** do this:
1. Search for your newly created bot's username in Telegram.
2. Open the chat with your bot.
3. Click the **"Start"** button at the bottom of the screen (or type `/start` and send it).

If you skip this step, the Python script will fail to send the alert and will log a `Bad Request: chat not found` error!
