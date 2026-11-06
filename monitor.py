#!/usr/bin/env python3
"""Check Apple's US pickup inventory for 256GB iPhone Duo in either color, and email on changes."""
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

PARTS = {"MK1E4LL/A": "256GB Star White", "MK1F4LL/A": "256GB Night Sky"}
ENDPOINT = "https://www.apple.com/shop/retail/pickup-message"
PRODUCT_URL = "https://www.apple.com/shop/buy-iphone/iphone-duo"
STATE = Path(os.environ.get("STATE_FILE", ".stock-state.json"))
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36"


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
    for store in stores:
        code = store.get("storeNumber")
        availability = store.get("partsAvailability")
        if not code or not isinstance(availability, dict):
            raise ValueError("Malformed store availability")
        print(f"Checking Apple Store: {store.get('storeName', code)} ({code})")
        for part in requested:
            detail = availability.get(part)
            if not isinstance(detail, dict):
                raise ValueError(f"Missing availability for {part} at {code}")
            status = detail.get("pickupDisplay")
            if status not in ("available", "unavailable", "ineligible"):
                raise ValueError(f"Unrecognized pickup status {status!r} at {code}")
            key = f"{code}:{part}"
            if status == "available":
                found[key] = {"store": store.get("storeName", code), "part": part, "capacity": requested[part], "store_number": code}
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


def send_email(hits, *, test=False, failure=False):
    host = os.environ["SMTP_HOST"]
    port = int(os.environ.get("SMTP_PORT") or "465")
    username = os.environ["SMTP_USER"]
    password = os.environ["SMTP_PASSWORD"]
    receiver = os.environ["ALERT_EMAIL"]
    msg = EmailMessage()
    msg["Subject"] = ("ACTION REQUIRED: Apple stock monitor failed" if failure else
                      "Apple stock monitor TEST" if test else
                      "IN STOCK: iPhone Duo 256GB for pickup!")
    msg["From"] = username
    msg["To"] = receiver
    msg.set_content(
        ("The scheduled stock monitor failed and may miss availability. Check https://github.com/alissaahodge/apple-stock-monitor/actions . This does not mean sold out." if failure else
         "Test email from Apple Stock Monitor." if test else
         "256GB iPhone Duo available for pickup:\n" +
         "\n".join(f"- {v['capacity']} at {v['store']} ({v['part']})\n  Directions: https://www.google.com/maps/search/?api=1&query={urllib.parse.quote('Apple ' + v['store'] + ' 95050')}" for v in hits.values()))
        + "\n\nOrder immediately (choose the listed pickup store): " + PRODUCT_URL + "\nConfirm unlocked / Connect Later at checkout."
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


def send_push(hits, *, test=False):
    token = os.getenv("PUSHOVER_APP_TOKEN")
    user = os.getenv("PUSHOVER_USER_KEY")
    if not token and not user and not test:
        return
    if not token or not user:
        raise RuntimeError("Set both PUSHOVER_APP_TOKEN and PUSHOVER_USER_KEY")
    message = ("Test alert only. No stock was checked." if test else
               "\n".join(f"{hit['capacity']} at {hit['store']}" for hit in hits.values()))
    data = urllib.parse.urlencode({
        "token": token,
        "user": user,
        "title": "TEST: Apple stock monitor" if test else "IN STOCK: iPhone Duo pickup",
        "message": message[:1024],
        "url": PRODUCT_URL,
        "url_title": "Open Apple order page",
        "priority": 2,
        "retry": 60,
        "expire": 300,
    }).encode()
    try:
        with urllib.request.urlopen("https://api.pushover.net/1/messages.json", data=data, timeout=20) as response:
            accepted = json.load(response).get("status") == 1
    except (OSError, ValueError, AttributeError):
        raise RuntimeError("Pushover request failed. Check the Actions secrets and Pushover service.") from None
    if not accepted:
        raise RuntimeError("Pushover did not accept the alert")
    print("Pushover accepted the alert")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-push", action="store_true")
    parser.add_argument("--test-email", action="store_true")
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--simulate-available", action="store_true")
    parser.add_argument("--failure-email", action="store_true")
    args = parser.parse_args()
    if args.test_push:
        send_push({}, test=True)
        return
    if args.failure_email:
        send_email({}, failure=True)
        print("Failure diagnostic email sent (see GitHub Actions for error)")
        return
    if args.simulate_available:
        send_email({"TEST:MK1E4LL/A": {"store": "SIMULATED Apple Store (not real stock)", "store_number": "TEST", "part": "MK1E4LL/A", "capacity": "256GB Star White"}})
        print("SIMULATED stock alert sent")
        return
    if args.test_email:
        send_email({}, test=True)
        print("Test email sent")
        return
    zip_code = os.environ.get("ZIP_CODE", "95050")
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
    if not isinstance(previous, dict):
        raise ValueError("Saved state must be an object")
    new_hits = {key: val for key, val in hits.items() if key not in previous}
    if new_hits:
        try:
            send_push(new_hits)
        finally:
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
