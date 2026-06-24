#!/bin/bash

# Get the absolute path of the current directory
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT_PATH="$DIR/fuel_alert.py"

# Find the path to the python3 executable
PYTHON_PATH=$(which python3)

# The cron expression for every 30 minutes.
# Note: this is the regular price-check run and intentionally omits the
# --update-locations flag, so the 'All-Locations' sheet is left untouched.
# To refresh that sheet, run manually: python3 fuel_alert.py --update-locations
CRON_EXP="*/30 * * * * cd $DIR && $PYTHON_PATH $SCRIPT_PATH >> $DIR/fuel_alert.log 2>&1"

# Check if the cron job already exists to avoid duplicates
(crontab -l 2>/dev/null | grep -F "$SCRIPT_PATH") >/dev/null 2>&1
if [ $? -eq 0 ]; then
    echo "Cron job already exists for $SCRIPT_PATH"
else
    # Add the new cron job
    (crontab -l 2>/dev/null; echo "$CRON_EXP") | crontab -
    echo "Successfully scheduled fuel_alert.py to run every 30 minutes."
    echo "Logs will be written to $DIR/fuel_alert.log"
fi
