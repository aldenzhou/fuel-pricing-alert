#!/usr/bin/env python3
"""Manual test harness: mimic real fuel price changes and verify alerting.

This drives the REAL alert-decision functions from ``fuel_alert.py``
(``parse_alert_threshold``, ``should_send_alert``, ``format_alert_message``)
against a set of hand-crafted, realistic price-change scenarios. It shows
exactly when an alert fires and how the per-location 'Alert Threshold ($/L)'
setting filters out small moves.

It does NOT touch the database or the live NSW API — every scenario supplies its
own old/new price, so results are precise and repeatable.

By default this is a DRY RUN: it prints a results table and sends nothing.
Pass --send to actually deliver each triggered alert to Telegram so you can see
real messages arrive on your device.

Usage:
    # Dry run — print the scenario table, send nothing
    python3 simulate_price_changes.py

    # Also send the triggered alerts to Telegram (uses DEVELOPER_CHAT_ID)
    python3 simulate_price_changes.py --send

    # Send the triggered alerts to a specific chat id
    python3 simulate_price_changes.py --send --chat-id 123456789

Exit code is non-zero if any scenario's actual alert decision disagrees with its
documented expectation, so this doubles as a sanity check.
"""

import argparse
import os
import sys

from fuel_alert import (
    DEVELOPER_CHAT_ID,
    format_alert_message,
    parse_alert_threshold,
    send_telegram_message,
    should_send_alert,
)

# Each scenario mimics a realistic NSW price movement (prices in c/L) for a
# given per-location threshold (entered as it would appear in the sheet, in
# dollars/L; "" means a blank cell = alert on any change). `expect_alert` is the
# documented expectation used to self-check the logic.
SCENARIOS = [
    # --- Blank threshold: alert on ANY change ---
    {"station": "Ampol Foodary Thornleigh", "fuel": "U91",
     "old": 189.9, "new": 191.7, "threshold": "",
     "expect_alert": True,
     "note": "Typical overnight +1.8c rise, no threshold -> alert"},
    {"station": "Ampol Foodary Thornleigh", "fuel": "DL",
     "old": 205.3, "new": 205.4, "threshold": "",
     "expect_alert": True,
     "note": "Tiny +0.1c wobble, no threshold -> alert"},
    {"station": "Shell Reddy Express Queanbeyan", "fuel": "U91",
     "old": 189.9, "new": 189.9, "threshold": "",
     "expect_alert": False,
     "note": "Price unchanged -> never alert"},

    # --- 10c threshold (sheet value 0.10): filter out small moves ---
    {"station": "Ampol Foodary Thornleigh", "fuel": "U91",
     "old": 189.9, "new": 191.7, "threshold": "0.10",
     "expect_alert": False,
     "note": "+1.8c rise below 10c threshold -> quiet"},
    {"station": "Ampol Foodary Thornleigh", "fuel": "U91",
     "old": 189.9, "new": 199.8, "threshold": "0.10",
     "expect_alert": False,
     "note": "+9.9c rise just below 10c threshold -> quiet"},
    {"station": "Ampol Foodary Thornleigh", "fuel": "U91",
     "old": 189.9, "new": 199.9, "threshold": "0.10",
     "expect_alert": True,
     "note": "+10.0c rise exactly at threshold -> alert"},
    {"station": "Ampol Foodary Thornleigh", "fuel": "P98",
     "old": 215.9, "new": 239.9, "threshold": "0.10",
     "expect_alert": True,
     "note": "+24c price-cycle spike -> alert"},
    {"station": "Ampol Foodary Thornleigh", "fuel": "E10",
     "old": 199.9, "new": 169.9, "threshold": "0.10",
     "expect_alert": True,
     "note": "-30c end-of-cycle drop -> alert (drops count too)"},

    # --- 5c threshold (sheet value 0.05) ---
    {"station": "Shell Reddy Express Queanbeyan", "fuel": "U91",
     "old": 189.9, "new": 193.9, "threshold": "0.05",
     "expect_alert": False,
     "note": "+4.0c rise below 5c threshold -> quiet"},
    {"station": "Shell Reddy Express Queanbeyan", "fuel": "U91",
     "old": 189.9, "new": 195.5, "threshold": "0.05",
     "expect_alert": True,
     "note": "+5.6c rise above 5c threshold -> alert"},
]


def run(send=False, chat_id=None):
    target_chat = chat_id or DEVELOPER_CHAT_ID
    if send and not target_chat:
        print("ERROR: --send requires a chat id. Pass --chat-id <id> or set "
              "DEVELOPER_CHAT_ID in .env.")
        return 2

    print(f"{'Station / Fuel':<34} {'Old':>7} {'New':>7} {'Diff':>7} "
          f"{'Thresh':>7} {'Alert':>6} {'OK':>4}")
    print("-" * 80)

    failures = 0
    sent = 0
    for s in SCENARIOS:
        threshold_cents = parse_alert_threshold(s["threshold"], s["station"])
        will_alert = should_send_alert(s["old"], s["new"], threshold_cents)
        diff = s["new"] - s["old"]

        ok = (will_alert == s["expect_alert"])
        if not ok:
            failures += 1

        thresh_label = "-" if threshold_cents is None else f"{threshold_cents:.1f}"
        label = f"{s['station'][:20]} {s['fuel']}"
        print(f"{label:<34} {s['old']:>7.1f} {s['new']:>7.1f} {diff:>+7.1f} "
              f"{thresh_label:>7} {('YES' if will_alert else 'no'):>6} "
              f"{('OK' if ok else 'FAIL'):>4}")
        print(f"    -> {s['note']}")

        if send and will_alert:
            msg = format_alert_message(s["fuel"], s["station"], s["old"], s["new"])
            send_telegram_message(target_chat, msg)
            sent += 1

    print("-" * 80)
    triggered = sum(1 for s in SCENARIOS
                    if should_send_alert(
                        s["old"], s["new"],
                        parse_alert_threshold(s["threshold"], s["station"])))
    print(f"Scenarios: {len(SCENARIOS)} | would alert: {triggered} | "
          f"expectation mismatches: {failures}")

    if send:
        print(f"Sent {sent} alert(s) to chat {target_chat}.")
    else:
        print("Dry run — no Telegram messages sent. Re-run with --send to deliver "
              "the triggered alerts.")

    return 1 if failures else 0


def main():
    parser = argparse.ArgumentParser(
        description="Mimic fuel price changes and verify alert + threshold logic.")
    parser.add_argument("--send", action="store_true",
                        help="Actually send the triggered alerts to Telegram "
                             "(default is a dry run that sends nothing).")
    parser.add_argument("--chat-id", default=None,
                        help="Telegram chat id to send alerts to when --send is "
                             "used. Defaults to DEVELOPER_CHAT_ID from .env.")
    args = parser.parse_args()
    return run(send=args.send, chat_id=args.chat_id)


if __name__ == "__main__":
    sys.exit(main())
