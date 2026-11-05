#!/usr/bin/env python3
"""Check Apple's US pickup inventory for Star White iPhone Duo, and email on changes."""
import argparse
import json
import os
import smtplib
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage
from pathlib import Path

PARTS = {"MK1E4LL/A": "256GB Star White"}
ENDPOINT = "https://www.apple.com/shop/retail/pickup-message"
PRODUCT_URL = "https://www.apple.com/shop/buy-iphone/iphone-duo"
STATE = Path(os.environ.get("STATE_FILE", ".stock-state.json"))
USER_AGENT = "Mozilla/5.0 AppleStockMonitor/1.0"


def parse_inventory(payload, requested):
    """Fail closed on unexpected payload shapes, never equating errors to sold out."""
    try:
        stores = payload["body"].get("stores")
        if stores is None:
            stores = payload["body"]["content"]["pickupMessage"]["stores"]
        if not isinstance(stores, list) or not stores:
            raise ValueError("Apple returned no store records")
    except (KeyError, TypeError) as exc:
        raise ValueError("Unexpected Apple inventory response") from exc
    found = {}
    checked = set()
    for store in stores:
        code = store.get("storeNumber")
        availability = store.get("partsAvailability")
        if not code or not isinstance(availability, dict):
            raise ValueError("Malformed store availability")
        for part in requested:
            detail = availability.get(part)
            if not isinstance(detail, dict):
                raise ValueError(f"Missing availability for {part} at {code}")
            status = detail.get("pickupDisplay")
            if status not in ("available", "unavailable", "ineligible"):
                raise ValueError(f"Unrecognized pickup status {status!r} at {code}")
            key = f"{code}:{part}"
            checked.add(key)
            if status == "available":
                found[key] = {"store": store.get("storeName", code), "part": part, "capacity": requested[part]}
    if not checked:
        raise ValueError("No products checked")
    return found


def fetch_inventory(zip_code, parts=PARTS):
    params = [("pl", "true"), ("mts.0", "regular"), ("location", zip_code)]
    params.extend((f"parts.{i}", part) for i, part in enumerate(parts))
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    request = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Referer": PRODUCT_URL,
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    })
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.load(response)
    return parse_inventory(payload, parts)


def send_email(hits, *, test=False):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or "465")
    username = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    receiver = os.environ["ALERT_EMAIL"]
    msg = EmailMessage()
    msg["Subject"] = "Apple stock monitor TEST" if test else "iPhone Duo Star White available for pickup!"
    msg["From"] = username
    msg["To"] = receiver
    msg.set_content(
        ("Test email from Apple Stock Monitor." if test else
         "Star White 256GB iPhone Duo available for pickup:\n" +
         "\n".join(f"- {v['capacity']} at {v['store']} ({v['part']})" for v in hits.values()))
        + "\n\nCheck availability immediately: " + PRODUCT_URL
    )
    phase = "connect"
    try:
        if port == 465:
            phase = "implicit TLS connection"
            client = smtplib.SMTP_SSL(host, port, timeout=20)
        else:
            phase = "connection"
            client = smtplib.SMTP(host, port, timeout=20)
        with client as smtp:
            if port != 465:
                phase = "STARTTLS"
                smtp.starttls()
            phase = "authentication"
            smtp.login(username, password)
            phase = "send"
            smtp.send_message(msg)
    except smtplib.SMTPSenderRefused as exc:
        # The numeric SMTP status is safe to log; the server text may contain addresses.
        raise RuntimeError(
            f"Yahoo rejected the envelope sender (SMTP {exc.smtp_code}). "
            "Confirm SMTP_USER is the full Yahoo mailbox address, not an alias."
        ) from None
    except (OSError, smtplib.SMTPException) as exc:
        # Do not log server replies, usernames, or credentials.
        raise RuntimeError(f"Yahoo SMTP failed during {phase}: {type(exc).__name__}") from None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-email", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.test_email:
        send_email({}, test=True)
        print("Test email sent")
        return
    zip_code = os.environ.get("ZIP_CODE", "94086")
    if not (zip_code.isdigit() and len(zip_code) == 5):
        raise ValueError("ZIP_CODE must be a five-digit US ZIP code")
    hits = fetch_inventory(zip_code)
    print(f"Validated Apple response: {len(hits)} available combinations")
    if args.validate_only:
        return
    missing = [name for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "ALERT_EMAIL") if not os.getenv(name)]
    if missing:
        raise RuntimeError("Email secrets are not configured: " + ", ".join(missing))
    previous = json.loads(STATE.read_text()) if STATE.exists() else {}
    new_hits = {key: val for key, val in hits.items() if key not in previous}
    if new_hits:
        send_email(new_hits)
        print(f"Sent email for {len(new_hits)} new stock results")
    else:
        print("No newly available products")
    STATE.write_text(json.dumps(hits, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (urllib.error.HTTPError, urllib.error.URLError, ValueError, RuntimeError, KeyError, OSError, smtplib.SMTPException) as exc:
        print(f"Stock check failed (NOT a sold-out result): {exc}", file=sys.stderr)
        sys.exit(1)
