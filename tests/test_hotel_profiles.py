import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from marketing_diagnosis import hotel_profiles
from scripts import s14_feishu_entry as entry
from scripts import s14_feishu_card_callback as callback


class SharedHotelProfileTest(unittest.TestCase):
    def test_s14_uses_same_hotel_profile_and_missing_dsn_does_not_fall_back(self):
        cache = Path(__file__).resolve().parents[1] / ".pytest_cache"
        cache.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=cache) as directory:
            root = Path(directory)
            profile = {"config_version": 1, "name": "酒店甲", "database": {"dsn": "mysql://reader@localhost/hotel_a"},
                       "feishu": {"bots": {"a-s14": {"kind": "s14", "app_id": "app-a", "app_secret": "test-secret"}}}}
            (root / "a.json").write_text(json.dumps(profile))
            with patch.dict(os.environ, {"HOTEL_OTA_HOTEL_CONFIG_DIR": directory, "S14_DB_DSN": "mysql://wrong/other"}):
                self.assertEqual(entry._config("a")["db_dsn"], profile["database"]["dsn"])
                self.assertNotIn("db_dsn", entry._config("missing"))
                self.assertEqual(entry._display_name("a"), "酒店甲")
                self.assertEqual(callback._load_bot_credentials()["app-a"]["hotel_id"], "a")
                self.assertEqual(hotel_profiles.view("s14_accounts")["bots"]["a-s14"]["app_id"], "app-a")
