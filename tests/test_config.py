import unittest

from nadlan_balagan.config import parse_search


VALID = {
    "id": "gush-30303", "title": "Test", "enabled": True,
    "location": {"kind": "gush_range", "from": 30303, "to": 30303},
    "filters": {"property_type": "דירת מגורים", "transaction_type": "הכל", "period": "last_12_months"},
}


class ConfigTests(unittest.TestCase):
    def test_parses_search(self):
        search = parse_search(VALID)
        self.assertEqual(search.gush_from, 30303)
        self.assertEqual(search.period, "last_12_months")

    def test_rejects_reversed_range(self):
        data = {**VALID, "location": {"kind": "gush_range", "from": 40, "to": 30}}
        with self.assertRaisesRegex(ValueError, "at least"):
            parse_search(data)

    def test_rejects_unknown_period(self):
        data = {**VALID, "filters": {**VALID["filters"], "period": "today"}}
        with self.assertRaisesRegex(ValueError, "filters.period"):
            parse_search(data)
