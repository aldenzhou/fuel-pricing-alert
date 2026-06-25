#!/bin/bash

# Get the absolute path of the current directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$DIR/fuel_alert.py"

# Use the project's virtual environment interpreter so the cron job runs with
# the same dependencies as a local run.
PYTHON_PATH="$DIR/.venv/bin/python"

# The script writes its own rotating log to logs/fuel_alert.log, so the cron
# entries discard stdout and capture only stderr (genuine uncaught crashes) to
# logs/cron_error.log. 'mkdir -p logs' guards the first run before the script
# has created the folder.

# The cron expression for every 30 minutes.
# Note: this is the regular price-check run and intentionally omits the
# --update-locations flag, so the 'All-Locations' sheet is left untouched.
# To refresh that sheet, run manually: .venv/bin/python fuel_alert.py --update-locations
CRON_EXP="*/30 * * * * cd $DIR && mkdir -p logs && $PYTHON_PATH fuel_alert.py >/dev/null 2>> $DIR/logs/cron_error.log"

# The cron expression for the weekly NSW locations refresh.
# Runs every Sunday at 03:00 and passes --update-locations to (re)populate the
# 'All-Locations' sheet with all NSW stations.
WEEKLY_CRON_EXP="0 3 * * 0 cd $DIR && mkdir -p logs && $PYTHON_PATH fuel_alert.py --update-locations >/dev/null 2>> $DIR/logs/cron_error.log"

# Check if the price-check cron job already exists to avoid duplicates
(crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH" | grep -v -- "--update-locations") >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Cron job already exists for the 30-minute price check."
else
    (crontab -l 2>/dev/null; echo "$CRON_EXP") | crontab -
    echo "Successfully scheduled fuel_alert.py to run every 30 minutes."
fi

# Check if the weekly locations-update cron job already exists to avoid duplicates
(crontab -l 2>/dev/null | grep -F -- "--update-locations") >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Cron job already exists for the weekly NSW locations refresh."
else
    (crontab -l 2>/dev/null; echo "$WEEKLY_CRON_EXP") | crontab -
    echo "Successfully scheduled a weekly NSW locations refresh (Sundays at 03:00)."
fi

echo "Logs will be written to $DIR/logs/fuel_alert.log (rotating; stderr to logs/cron_error.log)"
