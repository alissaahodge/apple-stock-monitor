import unittest
import tempfile
import os
import json
from pathlib import Path
from unittest.mock import patch
import monitor
from monitor import parse_inventory, PARTS


def payload(status="unavailable"):
    return {"body": {"content": {"pickupMessage": {"stores": [{
        "storeNumber": "R001", "storeName": "Test Store",
        "partsAvailability": {part: {"pickupDisplay": status} for part in PARTS}
    }]}}}}


class InventoryTests(unittest.TestCase):
    def test_unavailable(self):
        self.assertEqual(parse_inventory(payload(), PARTS), {})

    def test_available(self):
        self.assertEqual(len(parse_inventory(payload("available"), PARTS)), 1)

    def test_either_color_can_be_available(self):
        for available_part in PARTS:
            with self.subTest(part=available_part):
                response = payload()
                availability = response["body"]["content"]["pickupMessage"]["stores"][0]["partsAvailability"]
                availability[available_part]["pickupDisplay"] = "available"
                found = parse_inventory(response, PARTS)
                self.assertEqual(list(found), [f"R001:{available_part}"])
                self.assertEqual(found[f"R001:{available_part}"]["capacity"], PARTS[available_part])

    def test_both_colors_available(self):
        found = parse_inventory(payload("available"), PARTS)
        self.assertEqual(set(found), {f"R001:{part}" for part in PARTS})

    def test_missing_store_records(self):
        with self.assertRaises(ValueError):
            parse_inventory({"body": {"content": {"pickupMessage": {"stores": []}}}}, PARTS)

    def test_missing_part(self):
        bad = payload()
        del bad["body"]["content"]["pickupMessage"]["stores"][0]["partsAvailability"]["MK1E4LL/A"]
        with self.assertRaises(ValueError):
            parse_inventory(bad, PARTS)


    def test_alert_contains_store_and_directions(self):
        hits = parse_inventory(payload("available"), PARTS)
        with patch.dict(os.environ, {"ZIP_CODE": "95050", "SMTP_HOST": "test", "SMTP_USER": "sender@example.com", "SMTP_PASSWORD": "test", "ALERT_EMAIL": "recipient@example.com"}):
            class SMTP:
                def __init__(self, *args, **kwargs): pass
                def __enter__(self): return self
                def __exit__(self, *args): pass
                def login(self, *args): pass
                def send_message(self, msg):
                    self.msg = msg
                    self_test.messages.append(msg)
            self_test = self
            self.messages = []
            with patch("monitor.smtplib.SMTP_SSL", SMTP):
                monitor.send_email(hits)
            content = self.messages[0].get_content()
            self.assertIn("Test Store", content)
            self.assertIn("256GB Star White", content)
            self.assertIn("256GB Night Sky", content)
            self.assertIn("IN STOCK: iPhone Duo 256GB for pickup!", self.messages[0]["Subject"])
            self.assertIn("google.com/maps/search", content)
            self.assertIn("buy-iphone/iphone-duo", content)

    def test_stock_transition_emails_only_once(self):
        hits = parse_inventory(payload("available"), PARTS)
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(monitor, "STATE", Path(tmp) / "state.json"), patch.object(monitor, "fetch_inventory", return_value=hits), patch.object(monitor, "send_email") as email, patch("sys.argv", ["monitor.py"]), patch.dict(os.environ, {"ZIP_CODE": "95050", "SMTP_HOST": "test", "SMTP_USER": "test", "SMTP_PASSWORD": "test", "ALERT_EMAIL": "test"}):
                monitor.main()
                monitor.main()
                email.assert_called_once()

    def test_smtp_failure_does_not_save_state(self):
        hits = parse_inventory(payload("available"), PARTS)
        with tempfile.TemporaryDirectory() as tmp:
            state = Path(tmp) / "state.json"
            with patch.object(monitor, "STATE", state), patch.object(monitor, "fetch_inventory", return_value=hits), patch.object(monitor, "send_email", side_effect=RuntimeError("SMTP failed")), patch("sys.argv", ["monitor.py"]), patch.dict(os.environ, {"ZIP_CODE": "95050", "SMTP_HOST": "test", "SMTP_USER": "test", "SMTP_PASSWORD": "test", "ALERT_EMAIL": "test"}):
                with self.assertRaises(RuntimeError):
                    monitor.main()
                self.assertFalse(state.exists())

if __name__ == "__main__":
    unittest.main()
