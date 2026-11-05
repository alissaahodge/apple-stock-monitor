import unittest
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

    def test_missing_store_records(self):
        with self.assertRaises(ValueError):
            parse_inventory({"body": {"content": {"pickupMessage": {"stores": []}}}}, PARTS)

    def test_missing_part(self):
        bad = payload()
        del bad["body"]["content"]["pickupMessage"]["stores"][0]["partsAvailability"]["MK1E4LL/A"]
        with self.assertRaises(ValueError):
            parse_inventory(bad, PARTS)


if __name__ == "__main__":
    unittest.main()
